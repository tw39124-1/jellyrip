import threading
import time

from jellyrip.colors import cyan, dim

_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Spinner:
    def __init__(self, message: str):
        self._message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._start = 0.0

    def _run(self):
        i = 0
        while not self._stop.wait(0.05):
            elapsed = int(time.time() - self._start)
            m, s = divmod(elapsed, 60)
            print(
                f"\r  {cyan(_CHARS[i % len(_CHARS)])}  {self._message}  {dim(f'{m:02d}:{s:02d}')}\033[K",
                end="", flush=True,
            )
            i += 1

    def __enter__(self):
        self._start = time.time()
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join(timeout=2)
        print("\r\033[K", end="", flush=True)
