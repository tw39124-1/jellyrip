import argparse
import re
import shutil
import tempfile
from pathlib import Path

from jellyrip import state
from jellyrip.colors import bold, cyan, dim, green, red, yellow
from jellyrip.config import DEVICE, DISC_READY_TIMEOUT, FORBIDDEN_CHARS, OUTPUT_ROOT
from jellyrip.deps import check_dependencies
from jellyrip.disc import close_tray, open_tray, wait_for_disc, wait_for_tray_close
from jellyrip.jellyfin import eject, trigger_jellyfin_scan
from jellyrip.prompt import clean_label, prompt_title_year
from jellyrip.rip import get_disc_titles, rip_titles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEVICE, help="DVD drive device (default: %(default)s)")
    args = parser.parse_args()
    device = args.device
    disc_ref = f"{device}"
    state._device = device

    check_dependencies()

    while True:
        open_tray(device)

        result = wait_for_tray_close(device)
        if result == "quit":
            break
        if result == "enter":
            close_tray(device)

        raw_label = wait_for_disc(device)
        if not raw_label:
            print(f"\n  {red('ERROR:')} Disc not readable after {DISC_READY_TIMEOUT}s. Check the disc and try again.")
            continue

        title, year = prompt_title_year(clean_label(raw_label))
        movie_name = f"{title} ({year})"
        movie_dir = OUTPUT_ROOT / movie_name

        titles_info = get_disc_titles(disc_ref)
        main_id = max(titles_info, key=lambda t: t["duration_secs"])["id"]
        selected_ids = [main_id]
        main_title = next(t for t in titles_info if t["id"] == main_id)
        main_detail = f'({main_title["duration"]}, {main_title["size"]})'
        print(f'\n  {dim("Main feature:")} title {main_id + 1}  {dim(main_detail)}')

        if movie_dir.exists():
            print(f'\n  {yellow("WARNING:")} Output directory already exists: {dim(str(movie_dir))}')
            if input("  Continue anyway (may overwrite files)? [y/N]: ").strip().lower() != "y":
                continue

        state._temp_dir = Path(tempfile.mkdtemp(prefix="dvdrip_"))

        try:
            id_to_info = {t["id"]: t for t in titles_info}
            ripped = rip_titles(selected_ids, titles_info, state._temp_dir, disc_ref)

            for tid in selected_ids:
                source_mkv = ripped[tid]

                if tid == main_id:
                    output_path = movie_dir / f"{movie_name}.mkv"
                else:
                    info = id_to_info[tid]
                    default_name = f"Extra - {info['duration'].replace(':', 'h', 1).replace(':', 'm')}s"
                    raw_name = input(
                        f"\nName for title {tid + 1} ({info['duration']}) "
                        f'[{default_name}]: '
                    ).strip()
                    extra_name = re.sub(FORBIDDEN_CHARS, "", raw_name or default_name).strip()
                    output_path = movie_dir / "extras" / f"{extra_name}.mkv"

                output_path.parent.mkdir(parents=True, exist_ok=True)

                print(f"\n  Copying → {cyan(output_path.name)}...")
                shutil.copy2(source_mkv, output_path)
                print(f"  {green('✓')} {output_path.name}  {dim(f'({output_path.stat().st_size / 1e9:.1f} GB)')}")

            shutil.rmtree(state._temp_dir, ignore_errors=True)
            state._temp_dir = None

            print(f"\n  {green(bold('✓ Done!'))}")
            print(f"  {dim(str(movie_dir) + '/')}")
            print(f"\n  {dim('Triggering Jellyfin scan…')}")
            trigger_jellyfin_scan()
            eject(device)

        except SystemExit:
            raise
