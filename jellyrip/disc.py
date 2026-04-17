import subprocess
import time

from jellyrip.config import DEVICE, DISC_READY_TIMEOUT


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
