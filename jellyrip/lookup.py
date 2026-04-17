import json
import os
import re
import urllib.parse
import urllib.request


def lookup_movie_year(title: str) -> str | None:
    api_key = os.environ.get("OMDB_API_KEY", "")
    if not api_key:
        return None
    try:
        params = urllib.parse.urlencode({"t": title, "type": "movie", "apikey": api_key})
        with urllib.request.urlopen(f"https://www.omdbapi.com/?{params}", timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("Response") == "True":
            m = re.match(r"\d{4}", data.get("Year", ""))
            return m.group() if m else None
    except Exception:
        pass
    return None
