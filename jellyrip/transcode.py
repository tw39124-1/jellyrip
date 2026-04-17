import re
import subprocess
import sys
import threading
from fractions import Fraction
from pathlib import Path

from jellyrip import state


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


def transcode_with_handbrake(source: Path, output: Path, fps: str, label: str = ""):
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
    state._active_proc = proc

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

    state._active_proc = None
