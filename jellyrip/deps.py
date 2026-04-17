import shutil
import sys


def check_dependencies():
    missing = [t for t in ("eject", "blkid", "makemkvcon", "ffprobe")  # "HandBrakeCLI" temporarily removed
               if not shutil.which(t)]
    if missing:
        print(f"ERROR: Missing required tools: {', '.join(missing)}")
        print("  sudo apt install eject ffmpeg")
        print("  # MakeMKV: see makemkv.com/forum/viewtopic.php?t=224")
        sys.exit(1)
