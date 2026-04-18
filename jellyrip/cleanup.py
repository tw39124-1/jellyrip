import shutil
import subprocess

from jellyrip import state


def _kill_active_proc():
    if state._active_proc is not None and state._active_proc.poll() is None:
        state._active_proc.terminate()
        try:
            state._active_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            state._active_proc.kill()
    state._active_proc = None


def do_cleanup():
    print("\n  Stopping current process...", flush=True)
    _kill_active_proc()
    if state._temp_dir is not None and state._temp_dir.exists():
        print(f"  Removing temp files: {state._temp_dir}", flush=True)
        shutil.rmtree(state._temp_dir, ignore_errors=True)
        state._temp_dir = None
    print("  Ejecting disc...", flush=True)
    subprocess.run(["eject", state._device], capture_output=True)
    print("  Done.", flush=True)
