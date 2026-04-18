import fcntl
import os
import select
import subprocess
import sys
import threading
import time

from jellyrip.config import DEVICE, DISC_READY_TIMEOUT

CDROM_DRIVE_STATUS = 0x5326
CDS_DISC_OK = 4


def open_tray(device: str = DEVICE):
    print(f"Opening disc tray ({device})...")
    if subprocess.run(["eject", device]).returncode != 0:
        print("WARNING: Could not open tray (may already be open).")


def close_tray(device: str = DEVICE):
    print("Closing tray...")
    subprocess.run(["eject", "-t", device])


def wait_for_tray_close(device: str = DEVICE) -> str:
    """Wait for the user to close the tray.

    Returns 'quit' if user typed q, 'enter' if Enter was pressed (caller must
    call close_tray()), or 'hardware' if the tray was physically closed.
    """
    closed = threading.Event()

    def _poll():
        consecutive = 0
        while not closed.is_set():
            try:
                fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
                status = fcntl.ioctl(fd, CDROM_DRIVE_STATUS, 0)
                os.close(fd)
                if status == CDS_DISC_OK:
                    consecutive += 1
                    if consecutive >= 2:
                        closed.set()
                        return
                else:
                    consecutive = 0
            except Exception:
                consecutive = 0
            time.sleep(1)

    threading.Thread(target=_poll, daemon=True).start()
    print("\nInsert DVD. Press Enter to close tray, or close it manually (q to quit): ", end="", flush=True)

    result = "hardware"
    while not closed.is_set():
        if select.select([sys.stdin], [], [], 1.0)[0]:
            line = sys.stdin.readline().strip().lower()
            result = "quit" if line == "q" else "enter"
            closed.set()
            break

    return result


def wait_for_disc(device: str = DEVICE) -> str | None:
    from jellyrip.spinner import Spinner
    deadline = time.time() + DISC_READY_TIMEOUT
    with Spinner("Waiting for disc..."):
        while time.time() < deadline:
            result = subprocess.run(
                ["blkid", device, "-o", "value", "-s", "LABEL"],
                capture_output=True, text=True,
            )
            label = result.stdout.strip()
            if label:
                return label
            time.sleep(2)
    return None
