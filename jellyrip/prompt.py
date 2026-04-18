import re

from jellyrip.config import FORBIDDEN_CHARS
from jellyrip.lookup import lookup_movie, search_omdb


def clean_label(raw: str) -> str:
    title = raw.replace("_", " ").replace("-", " ")
    title = re.sub(FORBIDDEN_CHARS, "", title)
    return re.sub(r"\s+", " ", title).strip().title()


def _prompt_year() -> str:
    from jellyrip.colors import dim, yellow
    while True:
        year = input(f"  {yellow('Year (e.g. 2008):')} ").strip()
        if re.fullmatch(r"(18[8-9]\d|19\d\d|20[0-2]\d|2030)", year):
            return year
        print(f"  {dim('Enter a valid 4-digit year between 1888 and 2030.')}")


def _search_flow(query: str) -> tuple[str, str] | None:
    """Run an OMDb search and let user pick a result. Returns (title, year) or None to fall back."""
    from jellyrip.colors import bold, cyan, dim, yellow
    from jellyrip.spinner import Spinner

    with Spinner("Searching OMDb..."):
        results = search_omdb(query)

    if not results:
        print(f"  {dim('No results found.')}")
        return None

    print()
    for i, r in enumerate(results, 1):
        print(f"  {cyan(str(i))}.  {bold(r['title'])}  {dim('(' + r['year'] + ')')}")
    print(f"  {cyan('0')}.  {dim('None of these — enter manually')}")
    print()

    while True:
        choice = input(f"  {yellow('Pick a number:')} ").strip()
        if choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            r = results[int(choice) - 1]
            return r["title"], r["year"]
        print(f"  {dim('Enter a number between 0 and ' + str(len(results)) + '.')}")


def prompt_title_year(detected: str) -> tuple[str, str]:
    from jellyrip.colors import bold, cyan, dim, yellow
    from jellyrip.spinner import Spinner

    disc_title = re.sub(FORBIDDEN_CHARS, "", detected).strip()

    with Spinner("Looking up on OMDb..."):
        match = lookup_movie(disc_title)

    if match:
        omdb_title, year = match
        print(f'\n  {dim("Title:")} {bold(omdb_title)}  {dim("(via OMDb)")}')
        print(f"  {dim('Year: ')} {cyan(year)}  {dim('(via OMDb)')}")
        choice = input(f"\n  {yellow('Press Enter to confirm, or type a new title to search:')} ").strip()
        if not choice:
            return omdb_title, year
        result = _search_flow(choice)
        if result:
            return result
        # Manual fallback
        title = re.sub(FORBIDDEN_CHARS, "", choice).strip().title() or omdb_title
        return title, _prompt_year()
    else:
        print(f'\n  {dim("Title:")} {bold(disc_title)}  {dim("(from disc — not found on OMDb)")}')
        query = input(f"  {yellow('Press Enter to keep, or type a title to search OMDb:')} ").strip()
        if query:
            result = _search_flow(query)
            if result:
                return result
            # Manual fallback after failed search
            title = re.sub(FORBIDDEN_CHARS, "", query).strip().title() or disc_title
            return title, _prompt_year()
        # Keep disc label, prompt for year manually
        return disc_title, _prompt_year()
