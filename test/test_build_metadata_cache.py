import gzip
import importlib.util
import json
import os
import tempfile
from unittest import TestCase

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "build_metadata_cache.py"
)
_spec = importlib.util.spec_from_file_location("build_metadata_cache", _SCRIPT)
build_metadata_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_metadata_cache)


class TestCompactRecord(TestCase):
    def test_full_record(self):
        record = build_metadata_cache.compact_record(
            {
                "id": 1,
                "name": "Doom",
                "summary": "Demons.",
                "rating": 87.64,
                "total_rating_count": 900,
                "cover": {"image_id": "co1"},
                "genres": [{"name": "Shooter"}],
                "screenshots": [{"image_id": "sc1"}, {"image_id": "sc2"}],
                "involved_companies": [
                    {"developer": True, "publisher": False, "company": {"name": "id Software"}},
                    {"developer": False, "publisher": True, "company": {"name": "GT Interactive"}},
                    {"developer": True, "company": {}},  # company without a name is ignored
                ],
                "release_dates": [
                    {"date": 700000000, "platform": 6},
                    {"date": 755740800, "platform": 13},
                    {"date": 760000000, "platform": 13},
                ],
            }
        )
        self.assertEqual(
            record,
            {
                "name": "Doom",
                "summary": "Demons.",
                "release_date": 755740800,  # earliest DOS release, not the earliest overall
                "genres": ["Shooter"],
                "publisher": "GT Interactive",
                "developer": "id Software",
                "rating": 88,
                "cover": "co1",
                "screenshots": ["sc1", "sc2"],
                "popularity": 900,
            },
        )

    def test_falls_back_to_other_platform_release_date(self):
        record = build_metadata_cache.compact_record(
            {"name": "X", "release_dates": [{"date": 5, "platform": 6}, {"platform": 13}]}
        )
        self.assertEqual(record["release_date"], 5)

    def test_empty_fields_are_dropped(self):
        self.assertEqual(build_metadata_cache.compact_record({"id": 3, "name": "Bare"}), {"name": "Bare"})


class TestWriteSnapshot(TestCase):
    def test_deterministic_and_sorted(self):
        games = {"10": {"name": "B"}, "9": {"name": "A"}}
        with tempfile.TemporaryDirectory() as tempdir:
            first, second = os.path.join(tempdir, "a.gz"), os.path.join(tempdir, "b.gz")
            build_metadata_cache.write_snapshot(first, games, "2026-11-01")
            build_metadata_cache.write_snapshot(second, dict(reversed(games.items())), "2026-11-01")
            with open(first, "rb") as a, open(second, "rb") as b:
                self.assertEqual(a.read(), b.read())
            with gzip.open(first, "rt", encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(list(data["games"]), ["10", "9"])  # sort_keys: string order
        self.assertEqual(data["generated_at"], "2026-11-01")
        self.assertEqual(data["source"], "IGDB.com")
