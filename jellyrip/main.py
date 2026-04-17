import re
import shutil
import sys
import tempfile
from pathlib import Path

from jellyrip import state
from jellyrip.config import DISC_READY_TIMEOUT, FORBIDDEN_CHARS, OUTPUT_ROOT
from jellyrip.deps import check_dependencies
from jellyrip.disc import close_tray, open_tray, wait_for_disc
from jellyrip.jellyfin import maybe_eject, trigger_jellyfin_scan
from jellyrip.prompt import clean_label, prompt_title_year, select_titles
from jellyrip.rip import get_disc_titles, rip_titles
# from jellyrip.transcode import detect_fps, transcode_with_handbrake


def main():
    check_dependencies()
    open_tray()

    answer = input("\nInsert DVD and press Enter when ready (or 'q' to quit): ").strip().lower()
    if answer == "q":
        sys.exit(0)

    close_tray()

    raw_label = wait_for_disc()
    if not raw_label:
        print(f"\nERROR: Disc not readable after {DISC_READY_TIMEOUT}s. Check the disc and try again.")
        sys.exit(1)

    title, year = prompt_title_year(clean_label(raw_label))
    movie_name = f"{title} ({year})"
    movie_dir = OUTPUT_ROOT / movie_name

    titles_info = get_disc_titles()
    selected_ids, main_id = select_titles(titles_info)

    print(f'\nWill rip {len(selected_ids)} title(s) → "{movie_name}"')
    if input("Proceed? [y/N]: ").strip().lower() != "y":
        print("Cancelled.")
        sys.exit(0)

    # Transcode option temporarily disabled
    # print("\nTranscode with HandBrakeCLI, or copy the MakeMKV file as-is?")
    # print("  [1] Copy MKV directly  (fast, lossless, larger file ~4–8 GB)")
    # print("  [2] Transcode x264     (slow, smaller file ~1–2 GB)")
    # transcode_choice = input("Choice [1]: ").strip()
    # do_transcode = transcode_choice == "2"
    do_transcode = False

    if movie_dir.exists():
        print(f'\nWARNING: Output directory already exists: {movie_dir}')
        if input("Continue anyway (may overwrite files)? [y/N]: ").strip().lower() != "y":
            sys.exit(0)

    state._temp_dir = Path(tempfile.mkdtemp(prefix="dvdrip_"))

    try:
        id_to_info = {t["id"]: t for t in titles_info}
        ripped = rip_titles(selected_ids, titles_info, state._temp_dir)

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

            # if do_transcode:
            #     fps = detect_fps(source_mkv)
            #     label = "" if tid == main_id else output_path.stem
            #     transcode_with_handbrake(source_mkv, output_path, fps, label=label)
            # else:
            print(f"\nCopying{' extras/' if tid != main_id else ''} → {output_path.name}...")
            shutil.copy2(source_mkv, output_path)
            print(f"  Saved: {output_path.name}  ({output_path.stat().st_size / 1e9:.1f} GB)")

        shutil.rmtree(state._temp_dir, ignore_errors=True)
        state._temp_dir = None

        print(f"\n✓ Done!")
        print(f"  {movie_dir}/")
        print("\nTriggering Jellyfin scan…")
        trigger_jellyfin_scan()
        maybe_eject()

    except SystemExit:
        raise
