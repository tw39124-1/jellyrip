import re

from jellyrip.config import FORBIDDEN_CHARS
from jellyrip.lookup import lookup_movie_year


def clean_label(raw: str) -> str:
    title = raw.replace("_", " ").replace("-", " ")
    title = re.sub(FORBIDDEN_CHARS, "", title)
    return re.sub(r"\s+", " ", title).strip().title()


def prompt_title_year(detected: str) -> tuple[str, str]:
    from jellyrip.colors import bold, cyan, dim, yellow
    from jellyrip.spinner import Spinner
    title = re.sub(FORBIDDEN_CHARS, "", detected).strip()
    print(f'\n  {dim("Title:")} {bold(title)}')

    with Spinner("Looking up year..."):
        year = lookup_movie_year(title)

    if year:
        print(f"  {dim('Year: ')} {cyan(year)}  {dim('(via OMDb)')}")
        return title, year

    while True:
        year = input(f"  {yellow('Year (e.g. 2008):')} ").strip()
        if re.fullmatch(r"(18[8-9]\d|19\d\d|20[0-2]\d|2030)", year):
            return title, year
        print(f"  {dim('Enter a valid 4-digit year between 1888 and 2030.')}")
