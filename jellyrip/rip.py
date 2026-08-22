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


def get_disc_titles(disc_ref: str = "disc:0") -> list[dict]:
    from jellyrip.spinner import Spinner
    with Spinner("Scanning disc..."):
        #result = subprocess.run(
        #    ["makemkvcon", "-r", "info", disc_ref],
        #    capture_output=True, text=True,
        #)
        result = subprocess.run(
            ["lsdvd", "-Oj", "-x", "-q"],
            capture_output=True, text=True
        )

    result_json = json.loads(result.stdout)

    # TINFO:id,code,flags,"value"
    # Useful codes: 8=chapters, 9=duration, 10=size (human), 11=size (bytes), 27=filename
    raw: dict[int, dict] = {}
    # { id: {  } }

    for t in result_json["track"]:
        tid = int(t["ix"])
        raw[tid] = {
            "chapters": len(t["chapter"]),
            "duration_secs": int(t["length"])
        }

    titles = []
    for tid in sorted(raw):
        info = raw[tid]
        duration_secs = info.get("duration_secs", 0)
        try:
            size_bytes = int(info.get(11, 0))
        except ValueError:
            size_bytes = 0
        titles.append({
            "id": tid,
            "duration": duration_secs,
            "duration_secs": duration_secs,
            "chapters": info["chapters"],
            "size": info.get(10, "?"),
            "size_bytes": size_bytes,
            "filename": f"title_t{tid:02d}.mkv",
        })

    return titles


def _progress_bar(pct: float, width: int = 30) -> str:
    from jellyrip.colors import cyan, dim
    filled = int(width * pct / 100)
    return cyan("█" * filled) + dim("░" * (width - filled))


def _pulse_bar(tick: int, width: int = 30, head: int = 6) -> str:
    from jellyrip.colors import cyan, dim
    period = (width - head) * 2
    pos = tick % period
    if pos > width - head:
        pos = period - pos
    bar = ["░"] * width
    for j in range(head):
        idx = pos + j
        if 0 <= idx < width:
            bar[idx] = "█"
    bright = "".join(bar[pos:pos + head])
    left = "".join(bar[:pos])
    right = "".join(bar[pos + head:])
    return dim(left) + cyan(bright) + dim(right)


def _fmt_duration(secs: int) -> str:
    m, s = divmod(secs, 60)
    return f"{m:02d}:{s:02d}"


def _rip_one_title(title_id: int, tmpdir: Path, label: str, expected_bytes: int = 0, disc_ref: str = "disc:0"):
    """Rip a single title into tmpdir, showing live progress."""

    args = ["HandBrakeCLI", "-i", disc_ref, "--main-feature", "-o", f"{str(tmpdir)}/title_{title_id}.mkv", "-f", "av_mkv", "--all-audio", "--all-subtitles"]

    print(" ".joins(args))
    proc = subprocess.Popen(
        args,
        text=True,
        bufsize=1,
    )
    state._active_proc = proc

    if proc.wait() != 0:
        print(f"\nERROR: Handbrake failed ripping title {title_id}.")
        sys.exit(1)

    state._active_proc = None


def rip_titles(selected_ids: list[int], titles_info: list[dict], tmpdir: Path, disc_ref: str = "disc:0") -> dict[int, Path]:
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
        from jellyrip.colors import bold, cyan, dim
        print(f"\n  {dim(f'[{idx + 1}/{n_total}]')} Ripping {bold(label)}...")

        before = set(tmpdir.glob("*.mkv"))
        _rip_one_title(tid, tmpdir, label, expected_bytes=info.get("size_bytes", 0), disc_ref=disc_ref)
        after = set(tmpdir.glob("*.mkv"))

        new_files = after - before
        if not new_files:
            expected = tmpdir / info["filename"]
            if expected.exists():
                new_files = {expected}
            else:
                from jellyrip.colors import red
                print(f"  {red('ERROR:')} No MKV produced for title {tid + 1}.")
                sys.exit(1)

        result[tid] = sorted(new_files, key=lambda f: f.stat().st_size, reverse=True)[0]
        size_mb = result[tid].stat().st_size / (1024 * 1024)
        from jellyrip.colors import green, dim
        print(f"  {green('✓')} {result[tid].name}  {dim(f'({size_mb:.0f} MB)')}")

    return result
