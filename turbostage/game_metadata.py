"""Offline catalog of DOS game metadata.

TurboStage ships a snapshot of the IGDB metadata for every DOS game
(``content/game_metadata.json.gz``), so looking up and searching games needs
no network access and no API credentials. The snapshot is regenerated
locally with ``scripts/build_metadata_cache.py`` and committed.

Only images are fetched at runtime, straight from IGDB's public image CDN.
"""

import difflib
import gzip
import importlib.resources
import json
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

CATALOG_RESOURCE = "content/game_metadata.json.gz"
IMAGE_URL_TEMPLATE = "https://images.igdb.com/igdb/image/upload/{size}/{image_id}.jpg"
COVER_SIZE = "t_cover_big"
SCREENSHOT_SIZE = "t_screenshot_big"
SEARCH_LIMIT = 20

# Search match tiers, best first. Within a tier, more popular games rank higher.
_EXACT = 5
_COMPACT_EXACT = 4  # "wingcommander" == "wing commander"
_CONTAINS = 3  # every query word is in the title (ties: titles starting with the query first)
_FUZZY = 1  # every query word closely matches a title word (typos)
_NO_MATCH = 0
_FUZZY_TOKEN_MIN = 0.8  # how close a misspelled word must be

_STOP_WORDS = frozenset({"the", "a", "an", "of", "and", "in", "to"})
_ROMAN = {
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "xi": "11",
    "xii": "12",
    "xiii": "13",
}
# Single letters are numerals only after another word ("Ultima V", not "I Have No Mouth").
_ROMAN_SINGLE = {"i": "1", "v": "5", "x": "10"}


class MetadataUnavailable(Exception):
    """The bundled metadata snapshot is missing or unreadable."""


def image_url(image_id: str, size: str) -> str:
    """Build a public IGDB image URL from an image id (no credentials needed)."""
    return IMAGE_URL_TEMPLATE.format(size=size, image_id=image_id)


def normalize_title(text: str) -> tuple[str, ...]:
    """Lowercase, strip accents and punctuation, and turn roman numerals into digits."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = text.replace("&", " and ").replace("'", "")
    tokens = re.findall(r"[a-z0-9]+", text)
    normalized = []
    for i, token in enumerate(tokens):
        if token in _ROMAN:
            token = _ROMAN[token]
        elif i > 0 and token in _ROMAN_SINGLE:
            token = _ROMAN_SINGLE[token]
        normalized.append(token)
    return tuple(normalized)


def _content_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(t for t in tokens if t not in _STOP_WORDS) or tokens


@dataclass(frozen=True)
class _IndexEntry:
    igdb_id: int
    name: str
    tokens: tuple[str, ...]
    content: tuple[str, ...]
    compact: str
    popularity: int

    @classmethod
    def build(cls, igdb_id: int, name: str, popularity: int) -> "_IndexEntry":
        tokens = normalize_title(name)
        content = _content_tokens(tokens)
        return cls(igdb_id, name, tokens, content, "".join(content), popularity)


def _match(query: tuple[str, ...], query_content: tuple[str, ...], entry: _IndexEntry) -> tuple[int, float]:
    """Return (tier, closeness) of a title for a query; tier _NO_MATCH when it does not match.

    Closeness (0.8-1.0) only varies for fuzzy matches.
    """
    if query == entry.tokens or query_content == entry.content:
        return _EXACT, 1.0
    if "".join(query_content) == entry.compact:
        return _COMPACT_EXACT, 1.0
    title_words = set(entry.tokens)
    if all(word in title_words for word in query_content):
        return _CONTAINS, 1.0
    total = 0.0
    for word in query_content:
        best = 0.0
        for title_word in entry.content:
            matcher = difflib.SequenceMatcher(None, word, title_word)
            if matcher.real_quick_ratio() < _FUZZY_TOKEN_MIN or matcher.quick_ratio() < _FUZZY_TOKEN_MIN:
                continue
            best = max(best, matcher.ratio())
        if best < _FUZZY_TOKEN_MIN:
            return _NO_MATCH, 0.0
        total += best
    return _FUZZY, total / len(query_content)


class GameMetadataCatalog:
    """Read-only access to the bundled game metadata snapshot.

    The file is loaded on first use (thread-safe), so constructing the catalog
    at startup costs nothing.
    """

    def __init__(self, path: str | None = None):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] | None = None
        self._index: list[_IndexEntry] = []

    def _games(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._data is None:
                self._data = self._load()
                self._index = [
                    _IndexEntry.build(int(igdb_id), game.get("name") or "", int(game.get("popularity") or 0))
                    for igdb_id, game in self._data["games"].items()
                ]
            return self._data["games"]

    def _load(self) -> dict[str, Any]:
        try:
            if self._path is not None:
                with gzip.open(self._path, "rt", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                resource = importlib.resources.files("turbostage").joinpath(CATALOG_RESOURCE)
                with resource.open("rb") as raw, gzip.open(raw, "rt", encoding="utf-8") as f:
                    data = json.load(f)
        except (OSError, EOFError, ValueError) as e:
            logger.exception("Could not load the game metadata snapshot")
            raise MetadataUnavailable(f"game metadata unavailable: {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("games"), dict):
            raise MetadataUnavailable("game metadata snapshot has an unexpected format")
        return data

    @property
    def generated_at(self) -> str:
        """Date the snapshot was built (ISO format), or "" when unknown."""
        self._games()
        return str(self._data.get("generated_at") or "")

    def get_game_info(self, igdb_id: int) -> dict[str, Any] | None:
        """Return a game's details, or None when the snapshot does not know it."""
        game = self._games().get(str(igdb_id))
        if game is None:
            return None
        cover = game.get("cover")
        return {
            "name": game.get("name"),
            "summary": game.get("summary") or "",
            "cover_url": image_url(cover, COVER_SIZE) if cover else "",
            "release_date": game.get("release_date"),
            "genres": list(game.get("genres") or []),
            "publisher": game.get("publisher"),
            "developer": game.get("developer"),
            "rating": game.get("rating"),
            "screenshot_urls": [image_url(s, SCREENSHOT_SIZE) for s in game.get("screenshots") or []],
        }

    def search_games(self, search_query: str) -> list[dict[str, Any]]:
        """Return up to SEARCH_LIMIT games matching a title, best first, as {"id", "name"}."""
        self._games()
        query = normalize_title(search_query)
        if not query:
            return []
        query_content = _content_tokens(query)
        ranked = []
        for entry in self._index:
            tier, closeness = _match(query, query_content, entry)
            if tier == _NO_MATCH:
                continue
            # Popularity beats word order: "monkey island" -> "The Secret of
            # Monkey Island" before the less known "Monkey Island 2".
            starts_with = entry.content[: len(query_content)] == query_content
            key = (-tier, -closeness, -entry.popularity, not starts_with, len(entry.name), entry.name.lower())
            ranked.append((key, entry))
        ranked.sort(key=lambda item: item[0])
        return [{"id": entry.igdb_id, "name": entry.name} for _, entry in ranked[:SEARCH_LIMIT]]
