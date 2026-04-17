import subprocess
import sys
import threading
import time
from pathlib import Path

from jellyrip import state


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
            "id": tid,
            "duration": duration,
            "duration_secs": _dur_to_secs(duration),
            "chapters": info.get(8, "?"),
            "size": info.get(10, "?"),
            "filename": info.get(27, f"title_t{tid:02d}.mkv"),
        })

    return titles


def _progress_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def _rip_one_title(title_id: int, tmpdir: Path, label: str):
    """Rip a single title from disc:0 into tmpdir, showing live progress."""
    proc = subprocess.Popen(
        ["makemkvcon", "-r", "mkv", "disc:0", str(title_id), str(tmpdir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    state._active_proc = proc
    start_time = time.time()
    stop_spinner = threading.Event()

    def _spinner():
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while not stop_spinner.wait(0.5):
            elapsed = int(time.time() - start_time)
            total_mb = sum(f.stat().st_size for f in tmpdir.glob("*.mkv")) / (1024 * 1024)
            mins, secs = divmod(elapsed, 60)
            with state._print_lock:
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
                            with state._print_lock:
                                print(f"\r  [{bar}] {pct:5.1f}%  {op}", end="", flush=True)
                            last_pct = pct
                except ValueError:
                    pass

        elif line.startswith("MSG:"):
            parts = line[4:].split(",", 4)
            if len(parts) >= 4:
                msg = parts[3].strip('"')
                if msg and len(msg) > 5:
                    with state._print_lock:
                        print(f"\r{' ' * 80}\r  [makemkv] {msg}", flush=True)
                    last_pct = -1.0

    stop_spinner.set()
    spinner.join(timeout=2)
    print()

    if proc.wait() != 0:
        print(f"\nERROR: MakeMKV failed ripping title {title_id + 1}.")
        sys.exit(1)

    state._active_proc = None


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
            expected = tmpdir / info["filename"]
            if expected.exists():
                new_files = {expected}
            else:
                print(f"ERROR: No MKV produced for title {tid + 1}.")
                sys.exit(1)

        result[tid] = sorted(new_files, key=lambda f: f.stat().st_size, reverse=True)[0]
        size_mb = result[tid].stat().st_size / (1024 * 1024)
        print(f"  Saved: {result[tid].name}  ({size_mb:.0f} MB)")

    return result
