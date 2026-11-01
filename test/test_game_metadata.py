import gzip
import json
import os
import tempfile
from unittest import TestCase

from turbostage.game_metadata import GameMetadataCatalog, MetadataUnavailable, normalize_title

GAMES = {
    "1": {"name": "Doom", "popularity": 900, "cover": "co1", "screenshots": ["sc1", "sc2"], "genres": ["Shooter"]},
    "2": {"name": "Doom II: Hell on Earth", "popularity": 800},
    "3": {"name": "Ishar 2: Messengers of Doom", "popularity": 20},
    "4": {"name": "Wing Commander III: Heart of the Tiger", "popularity": 300},
    "5": {"name": "Wing Commander", "popularity": 400},
    "6": {"name": "The Secret of Monkey Island", "popularity": 950},
    "7": {"name": "Monkey Island 2: LeChuck's Revenge", "popularity": 700},
    "8": {"name": "Ultima V: Warriors of Destiny"},
    "9": {"name": "Commander Keen: Goodbye Galaxy!", "popularity": 100},
    "10": {
        "name": "Dark Castle",
        "summary": "A castle.",
        "release_date": 567907200,
        "publisher": "Mirrorsoft",
        "rating": 70,
    },
}


def _write_snapshot(path, games=GAMES, generated_at="2026-11-01"):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"generated_at": generated_at, "source": "IGDB.com", "games": games}, f)


class TestNormalizeTitle(TestCase):
    def test_roman_numerals_and_punctuation(self):
        self.assertEqual(normalize_title("Wing Commander III: Heart"), ("wing", "commander", "3", "heart"))
        self.assertEqual(normalize_title("Ultima V"), ("ultima", "5"))
        self.assertEqual(normalize_title("LeChuck's Revenge"), ("lechucks", "revenge"))

    def test_leading_single_letter_is_a_word(self):
        self.assertEqual(normalize_title("I Have No Mouth"), ("i", "have", "no", "mouth"))

    def test_accents_and_ampersand(self):
        self.assertEqual(normalize_title("Pokémon & Co"), ("pokemon", "and", "co"))


class TestGameMetadataCatalog(TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json.gz")
        os.close(fd)
        self.addCleanup(os.unlink, self.path)
        _write_snapshot(self.path)
        self.catalog = GameMetadataCatalog(self.path)

    def _names(self, query):
        return [g["name"] for g in self.catalog.search_games(query)]

    def test_get_game_info_builds_image_urls(self):
        info = self.catalog.get_game_info(1)
        self.assertEqual(info["cover_url"], "https://images.igdb.com/igdb/image/upload/t_cover_big/co1.jpg")
        self.assertEqual(
            info["screenshot_urls"],
            [
                "https://images.igdb.com/igdb/image/upload/t_screenshot_big/sc1.jpg",
                "https://images.igdb.com/igdb/image/upload/t_screenshot_big/sc2.jpg",
            ],
        )
        self.assertEqual(info["genres"], ["Shooter"])

    def test_get_game_info_fills_missing_fields(self):
        info = self.catalog.get_game_info(10)
        self.assertEqual(info["summary"], "A castle.")
        self.assertEqual(info["release_date"], 567907200)
        self.assertEqual(info["cover_url"], "")
        self.assertEqual(info["screenshot_urls"], [])
        self.assertEqual(info["genres"], [])
        self.assertIsNone(info["developer"])

    def test_unknown_game(self):
        self.assertIsNone(self.catalog.get_game_info(999))

    def test_generated_at(self):
        self.assertEqual(self.catalog.generated_at, "2026-11-01")

    def test_exact_match_first(self):
        self.assertEqual(self._names("doom")[0], "Doom")

    def test_popularity_orders_partial_matches(self):
        self.assertEqual(self._names("doom 2"), ["Doom II: Hell on Earth", "Ishar 2: Messengers of Doom"])
        self.assertEqual(self._names("monkey island")[0], "The Secret of Monkey Island")

    def test_roman_numerals_match_digits(self):
        self.assertEqual(self._names("wing commander 3"), ["Wing Commander III: Heart of the Tiger"])
        self.assertEqual(self._names("Ultima V"), ["Ultima V: Warriors of Destiny"])

    def test_glued_words(self):
        self.assertEqual(self._names("wingcommander")[0], "Wing Commander")

    def test_typo(self):
        self.assertEqual(self._names("comandr keen"), ["Commander Keen: Goodbye Galaxy!"])

    def test_no_match_and_empty_query(self):
        self.assertEqual(self.catalog.search_games("zzzzqq"), [])
        self.assertEqual(self.catalog.search_games("  !! "), [])

    def test_results_have_id_and_name(self):
        self.assertEqual(self.catalog.search_games("dark castle"), [{"id": 10, "name": "Dark Castle"}])

    def test_missing_file(self):
        catalog = GameMetadataCatalog(self.path + ".missing")
        with self.assertRaises(MetadataUnavailable):
            catalog.get_game_info(1)

    def test_corrupt_file(self):
        with open(self.path, "wb") as f:
            f.write(b"not gzip")
        with self.assertRaises(MetadataUnavailable):
            GameMetadataCatalog(self.path).search_games("doom")

    def test_wrong_format(self):
        with gzip.open(self.path, "wt", encoding="utf-8") as f:
            json.dump(["not", "a", "snapshot"], f)
        with self.assertRaises(MetadataUnavailable):
            GameMetadataCatalog(self.path).get_game_info(1)


class TestBundledSnapshot(TestCase):
    def test_bundled_snapshot_loads(self):
        catalog = GameMetadataCatalog()
        self.assertTrue(catalog.generated_at)
        self.assertEqual(catalog.search_games("Dark Castle")[0]["name"], "Dark Castle")
