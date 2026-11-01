"""Build turbostage/content/game_metadata.json.gz from IGDB.

Downloads the metadata of every DOS game on IGDB (plus any game of the online
TurboStage database that IGDB does not tag as DOS) and writes the compact,
offline snapshot that the app ships. Run it locally once in a while and
commit the result; it is not part of the app, nor of CI.

    IGDB_CLIENT_ID=... IGDB_CLIENT_SECRET=... python scripts/build_metadata_cache.py

The credentials are the Twitch application ones, see
https://api-docs.igdb.com/#account-creation
"""

import argparse
import datetime
import gzip
import io
import json
import os
import sys
import time

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "turbostage", "content", "game_metadata.json.gz")
ONLINE_DB_URL = "https://github.com/jberclaz/turbostage_data/raw/refs/heads/master/archive/database.json.gz"

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"
DOS_PLATFORM_ID = 13
PAGE_SIZE = 500  # IGDB maximum
REQUEST_INTERVAL_S = 0.3  # IGDB allows 4 requests/s
RETRIES = 5
TIMEOUT_S = 30

FIELDS = """fields name, summary, rating, total_rating_count, cover.image_id, genres.name, screenshots.image_id,
    involved_companies.publisher, involved_companies.developer, involved_companies.company.name,
    release_dates.date, release_dates.platform;"""


class IgdbApi:
    def __init__(self, client_id: str, client_secret: str):
        response = requests.post(
            TOKEN_URL,
            params={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        self._headers = {"Client-ID": client_id, "Authorization": f"Bearer {response.json()['access_token']}"}

    def query(self, body: str) -> list[dict]:
        for attempt in range(RETRIES + 1):
            time.sleep(REQUEST_INTERVAL_S)
            response = requests.post(GAMES_URL, headers=self._headers, data=body, timeout=TIMEOUT_S)
            if response.status_code == 429 and attempt < RETRIES:
                time.sleep(attempt + 1)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("unreachable")

    def all_dos_games(self) -> list[dict]:
        games, offset = [], 0
        while True:
            page = self.query(
                f"{FIELDS} where platforms = ({DOS_PLATFORM_ID}); sort id asc; limit {PAGE_SIZE}; offset {offset};"
            )
            games.extend(page)
            print(f"  fetched {len(games)} DOS games", file=sys.stderr)
            if len(page) < PAGE_SIZE:
                return games
            offset += PAGE_SIZE

    def games_by_id(self, igdb_ids: list[int]) -> list[dict]:
        games = []
        for start in range(0, len(igdb_ids), PAGE_SIZE):
            chunk = ",".join(str(i) for i in igdb_ids[start : start + PAGE_SIZE])
            games.extend(self.query(f"{FIELDS} where id = ({chunk}); limit {PAGE_SIZE};"))
        return games


def compact_record(game: dict) -> dict:
    """Reduce a raw IGDB game to the snapshot format (image ids, not URLs)."""
    developers, publishers = [], []
    for involved in game.get("involved_companies") or []:
        name = (involved.get("company") or {}).get("name")
        if not name:
            continue
        if involved.get("developer"):
            developers.append(name)
        if involved.get("publisher"):
            publishers.append(name)

    release_date = None
    release_dates = [rd for rd in game.get("release_dates") or [] if "date" in rd]
    if release_dates:
        dos = [rd for rd in release_dates if rd.get("platform") == DOS_PLATFORM_ID]
        release_date = min(rd["date"] for rd in (dos or release_dates))

    record = {
        "name": game.get("name") or "",
        "summary": game.get("summary") or "",
        "release_date": release_date,
        "genres": [g["name"] for g in game.get("genres") or [] if g.get("name")],
        "publisher": ", ".join(publishers) or None,
        "developer": ", ".join(developers) or None,
        "rating": int(round(game["rating"])) if game.get("rating") is not None else None,
        "cover": (game.get("cover") or {}).get("image_id"),
        "screenshots": [s["image_id"] for s in game.get("screenshots") or [] if s.get("image_id")],
        # Number of IGDB ratings: ranks well-known games first in title search.
        "popularity": game.get("total_rating_count") or None,
    }
    # Drop empty fields to keep the file small; the app treats missing as empty.
    return {k: v for k, v in record.items() if v not in (None, "", [])}


def online_database_ids(url: str) -> list[int]:
    response = requests.get(url, timeout=TIMEOUT_S)
    response.raise_for_status()
    data = json.loads(gzip.decompress(response.content))
    return sorted(int(i) for i in (data.get("games") or {}))


def write_snapshot(path: str, games: dict[str, dict], generated_at: str) -> int:
    """Write the snapshot deterministically (sorted keys, fixed gzip mtime); return its size."""
    payload = {"generated_at": generated_at, "source": "IGDB.com", "games": games}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as f:
        f.write(raw)
    with open(path, "wb") as f:
        f.write(buffer.getvalue())
    return len(buffer.getvalue())


def load_previous(path: str) -> dict:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f).get("games") or {}
    except (OSError, ValueError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="snapshot file to write")
    parser.add_argument("--online-db", default=ONLINE_DB_URL, help="TurboStage database whose games must be included")
    parser.add_argument("--no-online-db", action="store_true", help="only include games IGDB tags as DOS")
    args = parser.parse_args()

    client_id = os.environ.get("IGDB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("IGDB_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("error: set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET", file=sys.stderr)
        return 1

    api = IgdbApi(client_id, client_secret)
    print("Downloading DOS games from IGDB...", file=sys.stderr)
    raw_games = api.all_dos_games()
    games = {str(g["id"]): compact_record(g) for g in raw_games}

    if not args.no_online_db:
        missing = [i for i in online_database_ids(args.online_db) if str(i) not in games]
        if missing:
            print(f"Adding {len(missing)} game(s) of the online database not tagged as DOS", file=sys.stderr)
            games.update({str(g["id"]): compact_record(g) for g in api.games_by_id(missing)})

    previous = load_previous(args.output)
    size = write_snapshot(args.output, games, datetime.date.today().isoformat())
    added = len(games.keys() - previous.keys())
    removed = len(previous.keys() - games.keys())
    changed = sum(1 for k in games.keys() & previous.keys() if games[k] != previous[k])
    print(
        f"Wrote {len(games)} games to {args.output} ({size / 1e6:.2f} MB): "
        f"{added} added, {removed} removed, {changed} changed",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
