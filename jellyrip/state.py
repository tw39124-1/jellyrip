import subprocess
import threading
from pathlib import Path

# Tracked globally so KeyboardInterrupt cleanup can reach them.
_active_proc: subprocess.Popen | None = None
_temp_dir: Path | None = None

# Serialises terminal writes between the spinner thread and the line-parsing loop.
_print_lock = threading.Lock()
