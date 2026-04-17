import shutil
import sys


def check_dependencies():
    from jellyrip.colors import dim, red
    missing = [t for t in ("eject", "blkid", "makemkvcon", "ffprobe")  # "HandBrakeCLI" temporarily removed
               if not shutil.which(t)]
    if missing:
        print(f"  {red('ERROR:')} Missing required tools: {', '.join(missing)}")
        print(f"  {dim('sudo apt install eject ffmpeg')}")
        print(f"  {dim('# MakeMKV: see makemkv.com/forum/viewtopic.php?t=224')}")
        sys.exit(1)
