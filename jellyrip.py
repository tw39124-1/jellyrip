#!/usr/bin/env python3
"""DVD ripper — rips via MakeMKV then transcodes via HandBrakeCLI for Jellyfin."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from fractions import Fraction
from pathlib import Path

_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

DEVICE = "/dev/sr0"
OUTPUT_ROOT = Path("/srv/media/movies")
JELLYFIN_URL = "http://localhost:8096"
DISC_READY_TIMEOUT = 60
FORBIDDEN_CHARS = r'[<>:"/\\|?*]'

# Tracked globally so KeyboardInterrupt cleanup can reach them.
_active_proc: subprocess.Popen | None = None
_temp_dir: Path | None = None

# Serialises terminal writes between the spinner thread and the line-parsing loop.
_print_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def check_dependencies():
    missing = [t for t in ("eject", "blkid", "makemkvcon", "HandBrakeCLI", "ffprobe")
               if not shutil.which(t)]
    if missing:
        print(f"ERROR: Missing required tools: {', '.join(missing)}")
        print("  sudo apt install eject handbrake-cli ffmpeg")
        print("  # MakeMKV: see makemkv.com/forum/viewtopic.php?t=224")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Tray / disc
# ---------------------------------------------------------------------------

def open_tray():
    print(f"Opening disc tray ({DEVICE})...")
    if subprocess.run(["eject", DEVICE]).returncode != 0:
        print("WARNING: Could not open tray (may already be open).")


def close_tray():
    print("Closing tray...")
    subprocess.run(["eject", "-t", DEVICE])


def wait_for_disc() -> str | None:
    print(f"Waiting for disc to be ready (up to {DISC_READY_TIMEOUT}s)...", flush=True)
    deadline = time.time() + DISC_READY_TIMEOUT
    while time.time() < deadline:
        result = subprocess.run(
            ["blkid", DEVICE, "-o", "value", "-s", "LABEL"],
            capture_output=True, text=True,
        )
        label = result.stdout.strip()
        if label:
            return label
        time.sleep(5)
    return None


# ---------------------------------------------------------------------------
# Title / year prompt
# ---------------------------------------------------------------------------

def clean_label(raw: str) -> str:
    title = raw.replace("_", " ").replace("-", " ")
    title = re.sub(FORBIDDEN_CHARS, "", title)
    return re.sub(r"\s+", " ", title).strip().title()


def prompt_title_year(detected: str) -> tuple[str, str]:
    print(f'\nDetected disc title: "{detected}"')
    user_title = input("Press Enter to accept, or type a new title: ").strip()
    title = user_title if user_title else detected
    while True:
        year = input("Year (e.g. 2008): ").strip()
        if re.fullmatch(r"(18[8-9]\d|19\d\d|20[0-2]\d|2030)", year):
            break
        print("  Enter a valid 4-digit year between 1888 and 2030.")
    return re.sub(FORBIDDEN_CHARS, "", title).strip(), year


# ---------------------------------------------------------------------------
# Safe interrupt / cleanup
# ---------------------------------------------------------------------------

def _kill_active_proc():
    global _active_proc
    if _active_proc is not None and _active_proc.poll() is None:
        _active_proc.terminate()
        try:
            _active_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _active_proc.kill()
    _active_proc = None


def do_cleanup():
    global _temp_dir
    print("\n  Stopping current process...", flush=True)
    _kill_active_proc()
    if _temp_dir is not None and _temp_dir.exists():
        print(f"  Removing temp files: {_temp_dir}", flush=True)
        shutil.rmtree(_temp_dir, ignore_errors=True)
        _temp_dir = None
    print("  Ejecting disc...", flush=True)
    subprocess.run(["eject", DEVICE], capture_output=True)
    print("  Done.", flush=True)


# ---------------------------------------------------------------------------
# Disc title scanning
# ---------------------------------------------------------------------------

def _dur_to_secs(dur: str) -> int:
    try:
        h, m, s = dur.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception:
        return 0


def get_disc_titles() -> list[dict]:
    """Scan the disc with makemkvcon info and return a list of title dicts."""
    print("\nScanning disc for titles (this takes ~30 seconds)...", flush=True)

    result = subprocess.run(
        ["makemkvcon", "-r", "info", "disc:0"],
        capture_output=True, text=True,
    )

    # TINFO:id,code,flags,"value"
    # Useful codes: 8=chapters, 9=duration, 10=size (human), 11=size (bytes), 27=filename
    raw: dict[int, dict] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("TINFO:"):
            continue
        parts = line[6:].split(",", 3)
        if len(parts) < 4:
            continue
        try:
            tid, code = int(parts[0]), int(parts[1])
            value = parts[3].strip('"')
        except ValueError:
            continue
        raw.setdefault(tid, {})[code] = value

    titles = []
    for tid in sorted(raw):
        info = raw[tid]
        duration = info.get(9, "0:00:00")
        titles.append({
            "id": tid,                          # 0-based MakeMKV title index
            "duration": duration,
            "duration_secs": _dur_to_secs(duration),
            "chapters": info.get(8, "?"),
            "size": info.get(10, "?"),
            "filename": info.get(27, f"title_t{tid:02d}.mkv"),
        })

    return titles


def select_titles(titles: list[dict]) -> tuple[list[int], int]:
    """
    Show a table of titles and ask the user which to rip.
    Returns (selected_0based_ids, main_feature_0based_id).
    """
    if not titles:
        print("ERROR: No titles found on disc.")
        sys.exit(1)

    longest_id = max(titles, key=lambda t: t["duration_secs"])["id"]

    # ── table header ──────────────────────────────────────────────────────
    print()
    print(f"  {'#':>3}  {'Duration':>9}  {'Chapters':>8}  {'Size':>9}  Content")
    print("  " + "─" * 58)
    for t in titles:
        if t["id"] == longest_id:
            content = "Main Feature  ←  (longest)"
        elif t["duration_secs"] >= 2400:   # ≥ 40 min
            content = "Featurette / Long Bonus"
        elif t["duration_secs"] >= 120:    # ≥ 2 min
            content = "Bonus / Extra"
        else:
            content = "Short clip / Menu / Trailer"
        print(
            f"  {t['id'] + 1:>3}  {t['duration']:>9}  "
            f"{str(t['chapters']):>8}  {t['size']:>9}  {content}"
        )
    print()

    # ── title selection ───────────────────────────────────────────────────
    max_num = len(titles)
    while True:
        raw = input(
            f'Select titles to rip (e.g. "1", "1 3", "1-3", or "all"): '
        ).strip().lower()

        if raw == "all":
            selected = [t["id"] for t in titles]
            break

        selected = []
        valid = True
        for token in re.split(r"[\s,]+", raw):
            if not token:
                continue
            m = re.fullmatch(r"(\d+)-(\d+)", token)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 1 <= a <= max_num and 1 <= b <= max_num and a <= b:
                    selected.extend(i - 1 for i in range(a, b + 1))
                else:
                    valid = False; break
            elif token.isdigit():
                n = int(token)
                if 1 <= n <= max_num:
                    selected.append(n - 1)
                else:
                    valid = False; break
            else:
                valid = False; break

        # deduplicate while preserving order
        seen: set[int] = set()
        selected = [x for x in selected if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

        if valid and selected:
            break
        print(f"  Invalid. Enter numbers 1–{max_num}, ranges like 1-3, or 'all'.")

    # ── if multiple titles, confirm which is the main feature ─────────────
    if len(selected) == 1:
        main_id = selected[0]
    else:
        default_main = longest_id if longest_id in selected else selected[0]
        print(f"\nSelected: {[i + 1 for i in selected]}")
        raw_main = input(
            f"Which title is the main feature? [{default_main + 1}]: "
        ).strip()
        if raw_main.isdigit() and (int(raw_main) - 1) in selected:
            main_id = int(raw_main) - 1
        else:
            main_id = default_main
            if raw_main:
                print(f"  Keeping default: title {main_id + 1}.")

    return selected, main_id


# ---------------------------------------------------------------------------
# MakeMKV — rip with spinner + structured progress
# ---------------------------------------------------------------------------

def _progress_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def _rip_one_title(title_id: int, tmpdir: Path, label: str):
    """Rip a single title from disc:0 into tmpdir, showing live progress."""
    global _active_proc

    proc = subprocess.Popen(
        ["makemkvcon", "-r", "mkv", "disc:0", str(title_id), str(tmpdir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    _active_proc = proc
    start_time = time.time()
    stop_spinner = threading.Event()

    def _spinner():
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while not stop_spinner.wait(0.5):
            elapsed = int(time.time() - start_time)
            total_mb = sum(f.stat().st_size for f in tmpdir.glob("*.mkv")) / (1024 * 1024)
            mins, secs = divmod(elapsed, 60)
            with _print_lock:
                print(
                    f"\r  {chars[i % len(chars)]}  {mins:02d}:{secs:02d} elapsed"
                    f"  —  {total_mb:.0f} MB written to disk",
                    end="", flush=True,
                )
            i += 1

    spinner = threading.Thread(target=_spinner, daemon=True)
    spinner.start()

    current_op = label
    last_pct = -1.0

    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")

        if line.startswith("PRGC:"):
            parts = line[5:].split(",", 2)
            if len(parts) >= 3:
                current_op = parts[2].strip('"') or label

        elif line.startswith("PRGV:"):
            parts = line[5:].split(",")
            if len(parts) >= 3:
                try:
                    curr, maxx = int(parts[0]), int(parts[2])
                    if maxx > 0:
                        pct = min(curr / maxx * 100, 100.0)
                        if pct - last_pct >= 2.0 or pct >= 100.0:
                            bar = _progress_bar(pct)
                            op = current_op[:35].ljust(35)
                            with _print_lock:
                                print(f"\r  [{bar}] {pct:5.1f}%  {op}", end="", flush=True)
                            last_pct = pct
                except ValueError:
                    pass

        elif line.startswith("MSG:"):
            parts = line[4:].split(",", 4)
            if len(parts) >= 4:
                msg = parts[3].strip('"')
                if msg and len(msg) > 5:
                    with _print_lock:
                        print(f"\r{' ' * 80}\r  [makemkv] {msg}", flush=True)
                    last_pct = -1.0

    stop_spinner.set()
    spinner.join(timeout=2)
    print()

    if proc.wait() != 0:
        print(f"\nERROR: MakeMKV failed ripping title {title_id + 1}.")
        sys.exit(1)

    _active_proc = None


def rip_titles(selected_ids: list[int], titles_info: list[dict], tmpdir: Path) -> dict[int, Path]:
    """
    Rip each selected title into tmpdir.
    Returns {title_id: mkv_path}.
    """
    id_to_info = {t["id"]: t for t in titles_info}
    result: dict[int, Path] = {}

    for idx, tid in enumerate(selected_ids):
        info = id_to_info[tid]
        label = f"Title {tid + 1}  ({info['duration']})"
        n_total = len(selected_ids)
        print(f"\n[{idx + 1}/{n_total}] Ripping {label}...")

        before = set(tmpdir.glob("*.mkv"))
        _rip_one_title(tid, tmpdir, label)
        after = set(tmpdir.glob("*.mkv"))

        new_files = after - before
        if not new_files:
            # Fall back: look for the expected filename
            expected = tmpdir / info["filename"]
            if expected.exists():
                new_files = {expected}
            else:
                print(f"ERROR: No MKV produced for title {tid + 1}.")
                sys.exit(1)

        # There should be exactly one new file per rip
        result[tid] = sorted(new_files, key=lambda f: f.stat().st_size, reverse=True)[0]
        size_mb = result[tid].stat().st_size / (1024 * 1024)
        print(f"  Saved: {result[tid].name}  ({size_mb:.0f} MB)")

    return result


# ---------------------------------------------------------------------------
# Framerate detection
# ---------------------------------------------------------------------------

def detect_fps(mkv: Path) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(mkv)],
        capture_output=True, text=True,
    )
    raw = result.stdout.strip()
    try:
        fps = float(Fraction(raw))
        if abs(fps - 29.97) < 0.1 or abs(fps - 59.94) < 0.1:
            return "29.97"
        if abs(fps - 25.0) < 0.1 or abs(fps - 50.0) < 0.1:
            return "25"
        return str(round(fps, 3))
    except Exception:
        print(f"WARNING: Could not detect framerate ('{raw}'), defaulting to 29.97")
        return "29.97"


# ---------------------------------------------------------------------------
# HandBrakeCLI — transcode with live progress line
# ---------------------------------------------------------------------------

def transcode_with_handbrake(source: Path, output: Path, fps: str, label: str = ""):
    global _active_proc
    tag = f"  ({label})" if label else ""
    print(f"\nTranscoding{tag}...")
    print(f"  Source : {source.name}")
    print(f"  Output : {output}")
    print(f"  FPS    : {fps}")
    if not label:
        print("  Note   : x264 veryslow takes 2–4 hours for a feature film.\n")
    else:
        print()

    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "HandBrakeCLI",
        "-i", str(source), "-o", str(output),
        "-f", "mkv",
        "-e", "x264", "-q", "20",
        "--encoder-preset", "veryslow",
        "--encoder-profile", "high",
        "--encoder-level", "3.1",
        "--x264-tune", "film",
        "--decomb=eedi2bob",
        "--rate", fps, "--cfr",
        "--auto-anamorphic",
        "--audio-lang-list", "eng", "--all-audio",
        "--aencoder", "copy:ac3", "--audio-fallback", "aac", "--ab", "192",
        "--subtitle-lang-list", "eng", "--all-subtitles",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _active_proc = proc

    # HandBrake uses \r for progress — read in a background thread.
    def _read_handbrake():
        buf = ""
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            buf += chunk
            parts = re.split(r"[\r\n]", buf)
            buf = parts[-1]
            for part in parts[:-1]:
                part = part.strip()
                if not part:
                    continue
                if part.startswith(("Encoding:", "Muxing:")):
                    print(f"\r  {part:<78}", end="", flush=True)
                elif part:
                    print(f"\n  {part}", flush=True)

    stderr_chunks: list[str] = []

    def _read_stderr():
        for line in proc.stderr:
            stderr_chunks.append(line)

    reader = threading.Thread(target=_read_handbrake, daemon=True)
    stderr_reader = threading.Thread(target=_read_stderr, daemon=True)
    reader.start()
    stderr_reader.start()
    proc.wait()
    reader.join(timeout=3)
    stderr_reader.join(timeout=3)
    stderr_output = "".join(stderr_chunks)
    print()

    if proc.returncode != 0:
        print(f"\nERROR: HandBrakeCLI failed (exit {proc.returncode}). Temp files preserved at: {source.parent}")
        if stderr_output.strip():
            print(f"  HandBrake stderr:\n{stderr_output.strip()}")
        sys.exit(1)

    if not output.exists() or output.stat().st_size == 0:
        print(f"\nERROR: HandBrakeCLI exited 0 but output file is missing or empty.")
        if stderr_output.strip():
            print(f"  HandBrake stderr:\n{stderr_output.strip()}")
        print(f"  Temp files preserved at: {source.parent}")
        sys.exit(1)

    _active_proc = None


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def trigger_jellyfin_scan() -> None:
    api_key = os.environ.get("JELLYFIN_API_KEY")
    if not api_key:
        print("  (JELLYFIN_API_KEY not set — skipping library scan)")
        return
    req = urllib.request.Request(
        f"{JELLYFIN_URL}/Library/Refresh",
        method="POST",
        headers={"Authorization": f'MediaBrowser Token="{api_key}"'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                print("  Jellyfin library scan triggered.")
            else:
                print(f"  Jellyfin responded {resp.status} — scan may not have started.")
    except Exception as exc:
        print(f"  Could not reach Jellyfin: {exc}")


def maybe_eject():
    if input("\nEject disc? [Y/n]: ").strip().lower() != "n":
        subprocess.run(["eject", DEVICE])


def main():
    global _temp_dir

    check_dependencies()
    open_tray()

    answer = input("\nInsert DVD and press Enter when ready (or 'q' to quit): ").strip().lower()
    if answer == "q":
        sys.exit(0)

    close_tray()

    raw_label = wait_for_disc()
    if not raw_label:
        print(f"\nERROR: Disc not readable after {DISC_READY_TIMEOUT}s. Check the disc and try again.")
        sys.exit(1)

    title, year = prompt_title_year(clean_label(raw_label))
    movie_name = f"{title} ({year})"
    movie_dir = OUTPUT_ROOT / movie_name

    # Scan disc and let user choose titles
    titles_info = get_disc_titles()
    selected_ids, main_id = select_titles(titles_info)

    # Confirm before starting the long rip
    print(f'\nWill rip {len(selected_ids)} title(s) → "{movie_name}"')
    if input("Proceed? [y/N]: ").strip().lower() != "y":
        print("Cancelled.")
        sys.exit(0)

    print("\nTranscode with HandBrakeCLI, or copy the MakeMKV file as-is?")
    print("  [1] Copy MKV directly  (fast, lossless, larger file ~4–8 GB)")
    print("  [2] Transcode x264     (slow, smaller file ~1–2 GB)")
    transcode_choice = input("Choice [1]: ").strip()
    do_transcode = transcode_choice == "2"

    if movie_dir.exists():
        print(f'\nWARNING: Output directory already exists: {movie_dir}')
        if input("Continue anyway (may overwrite files)? [y/N]: ").strip().lower() != "y":
            sys.exit(0)

    _temp_dir = Path(tempfile.mkdtemp(prefix="dvdrip_"))

    try:
        # ── Rip ───────────────────────────────────────────────────────────
        id_to_info = {t["id"]: t for t in titles_info}
        ripped = rip_titles(selected_ids, titles_info, _temp_dir)

        # ── Transcode or copy ─────────────────────────────────────────────
        for tid in selected_ids:
            source_mkv = ripped[tid]

            if tid == main_id:
                output_path = movie_dir / f"{movie_name}.mkv"
            else:
                info = id_to_info[tid]
                default_name = f"Extra - {info['duration'].replace(':', 'h', 1).replace(':', 'm')}s"
                raw_name = input(
                    f"\nName for title {tid + 1} ({info['duration']}) "
                    f'[{default_name}]: '
                ).strip()
                extra_name = re.sub(FORBIDDEN_CHARS, "", raw_name or default_name).strip()
                output_path = movie_dir / "extras" / f"{extra_name}.mkv"

            output_path.parent.mkdir(parents=True, exist_ok=True)

            if do_transcode:
                fps = detect_fps(source_mkv)
                label = "" if tid == main_id else output_path.stem
                transcode_with_handbrake(source_mkv, output_path, fps, label=label)
            else:
                print(f"\nCopying{' extras/' if tid != main_id else ''} → {output_path.name}...")
                shutil.copy2(source_mkv, output_path)
                print(f"  Saved: {output_path.name}  ({output_path.stat().st_size / 1e9:.1f} GB)")

        # ── Cleanup ───────────────────────────────────────────────────────
        shutil.rmtree(_temp_dir, ignore_errors=True)
        _temp_dir = None

        print(f"\n✓ Done!")
        print(f"  {movie_dir}/")
        print("\nTriggering Jellyfin scan…")
        trigger_jellyfin_scan()
        maybe_eject()

    except SystemExit:
        raise  # error already printed; temp files preserved for inspection


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted!", flush=True)
        try:
            confirm = input("Cancel rip and clean up temp files? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            confirm = "y"
            print()
        if confirm == "y":
            do_cleanup()
        sys.exit(1)
