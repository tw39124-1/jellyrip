import re
import sys

from jellyrip.config import FORBIDDEN_CHARS


def clean_label(raw: str) -> str:
    title = raw.replace("_", " ").replace("-", " ")
    title = re.sub(FORBIDDEN_CHARS, "", title)
    return re.sub(r"\s+", " ", title).strip().title()


def prompt_title_year(detected: str) -> tuple[str, str]:
    print(f'\nDetected disc title: "{detected}"')
    user_title = input("Press Enter to accept, or type a new title: ").strip()
    title = user_title if user_title else detected
    while True:
        year = input("Year (e.g. 2008): ").strip()
        if re.fullmatch(r"(18[8-9]\d|19\d\d|20[0-2]\d|2030)", year):
            break
        print("  Enter a valid 4-digit year between 1888 and 2030.")
    return re.sub(FORBIDDEN_CHARS, "", title).strip(), year


def select_titles(titles: list[dict]) -> tuple[list[int], int]:
    if not titles:
        print("ERROR: No titles found on disc.")
        sys.exit(1)

    longest_id = max(titles, key=lambda t: t["duration_secs"])["id"]

    print()
    print(f"  {'#':>3}  {'Duration':>9}  {'Chapters':>8}  {'Size':>9}  Content")
    print("  " + "─" * 58)
    for t in titles:
        if t["id"] == longest_id:
            content = "Main Feature  ←  (longest)"
        elif t["duration_secs"] >= 2400:
            content = "Featurette / Long Bonus"
        elif t["duration_secs"] >= 120:
            content = "Bonus / Extra"
        else:
            content = "Short clip / Menu / Trailer"
        print(
            f"  {t['id'] + 1:>3}  {t['duration']:>9}  "
            f"{str(t['chapters']):>8}  {t['size']:>9}  {content}"
        )
    print()

    max_num = len(titles)
    while True:
        raw = input(
            f'Select titles to rip (e.g. "1", "1 3", "1-3", or "all"): '
        ).strip().lower()

        if raw == "all":
            selected = [t["id"] for t in titles]
            break

        selected = []
        valid = True
        for token in re.split(r"[\s,]+", raw):
            if not token:
                continue
            m = re.fullmatch(r"(\d+)-(\d+)", token)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 1 <= a <= max_num and 1 <= b <= max_num and a <= b:
                    selected.extend(i - 1 for i in range(a, b + 1))
                else:
                    valid = False; break
            elif token.isdigit():
                n = int(token)
                if 1 <= n <= max_num:
                    selected.append(n - 1)
                else:
                    valid = False; break
            else:
                valid = False; break

        seen: set[int] = set()
        selected = [x for x in selected if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

        if valid and selected:
            break
        print(f"  Invalid. Enter numbers 1–{max_num}, ranges like 1-3, or 'all'.")

    if len(selected) == 1:
        main_id = selected[0]
    else:
        default_main = longest_id if longest_id in selected else selected[0]
        print(f"\nSelected: {[i + 1 for i in selected]}")
        raw_main = input(
            f"Which title is the main feature? [{default_main + 1}]: "
        ).strip()
        if raw_main.isdigit() and (int(raw_main) - 1) in selected:
            main_id = int(raw_main) - 1
        else:
            main_id = default_main
            if raw_main:
                print(f"  Keeping default: title {main_id + 1}.")

    return selected, main_id
