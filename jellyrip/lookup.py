import json
import os
import re
import urllib.parse
import urllib.request


def _omdb_request(params: dict) -> dict | None:
    api_key = os.environ.get("OMDB_API_KEY", "")
    if not api_key:
        return None
    try:
        params["apikey"] = api_key
        query = urllib.parse.urlencode(params)
        with urllib.request.urlopen(f"https://www.omdbapi.com/?{query}", timeout=5) as resp:
            data = json.loads(resp.read())
        return data if data.get("Response") == "True" else None
    except Exception:
        return None


def lookup_movie(title: str) -> tuple[str, str] | None:
    data = _omdb_request({"t": title, "type": "movie"})
    if not data:
        return None
    m = re.match(r"\d{4}", data.get("Year", ""))
    year = m.group() if m else None
    omdb_title = data.get("Title", "").strip()
    if omdb_title and year:
        return omdb_title, year
    return None


def search_omdb(query: str) -> list[dict]:
    data = _omdb_request({"s": query, "type": "movie"})
    if not data:
        return []
    results = []
    for item in data.get("Search", [])[:5]:
        title = item.get("Title", "").strip()
        m = re.match(r"\d{4}", item.get("Year", ""))
        year = m.group() if m else "?"
        if title:
            results.append({"title": title, "year": year})
    return results
