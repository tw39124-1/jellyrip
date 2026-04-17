import os
import re
from pathlib import Path

_env_file = Path(__file__).parent.parent / ".env"
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
