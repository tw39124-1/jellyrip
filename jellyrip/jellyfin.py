import os
import subprocess
import urllib.request

from jellyrip.config import DEVICE, JELLYFIN_URL


def trigger_jellyfin_scan() -> None:
    api_key = os.environ.get("JELLYFIN_API_KEY")
    if not api_key:
        print("  (JELLYFIN_API_KEY not set — skipping library scan)")
        return
    req = urllib.request.Request(
        f"{JELLYFIN_URL}/Library/Refresh",
        method="POST",
        headers={"Authorization": f'MediaBrowser Token="{api_key}"'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                print("  Jellyfin library scan triggered.")
            else:
                print(f"  Jellyfin responded {resp.status} — scan may not have started.")
    except Exception as exc:
        print(f"  Could not reach Jellyfin: {exc}")


def eject():
    subprocess.run(["eject", DEVICE])
