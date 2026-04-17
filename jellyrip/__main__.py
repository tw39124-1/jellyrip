import sys

from jellyrip.cleanup import do_cleanup
from jellyrip.main import main


def run():
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted!", flush=True)
        try:
            confirm = input("Cancel rip and clean up temp files? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            confirm = "y"
            print()
        if confirm == "y":
            do_cleanup()
        sys.exit(1)


if __name__ == "__main__":
    run()
