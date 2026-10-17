import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase, GameDetails
from turbostage.fetch_game_info_thread import FetchGameInfoWorker

IGDB_ID = 4242
SCREENSHOTS = ["https://images.igdb.com/1.jpg", "https://images.igdb.com/2.jpg"]


class TestFetchGameInfoWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.unlink, self.db_path)
        DatabaseManager.initialize_database(self.db_path)
        db = GameDatabase(self.db_path)
        # A game added offline: no release date, so the worker asks IGDB.
        db.insert_game_with_details(
            "Game",
            GameDetails("Game", None, "", "", "", "", "", None, IGDB_ID, []),
        )
        db.close()

        self.igdb = MagicMock()
        self.igdb.get_game_info.return_value = {
            "summary": "A game",
            "cover_url": "",
            "release_date": 946684800,
            "genres": ["Adventure"],
            "publisher": "Pub",
            "developer": "Dev",
            "rating": 81.6,
            "screenshot_urls": SCREENSHOTS,
        }

    def _run_worker(self):
        worker = FetchGameInfoWorker(IGDB_ID, self.igdb, self.db_path, lambda: False)
        emitted = []
        worker.finished.connect(lambda *args: emitted.append(args))
        worker.run()
        self.assertEqual(len(emitted), 1)
        return emitted[0]

    def test_first_fetch_emits_screenshots(self):
        args = self._run_worker()
        self.assertEqual(json.loads(args[6]), SCREENSHOTS)
        self.assertEqual(args[5], "Dev")
        self.assertEqual(args[7], 82)

    def test_first_fetch_caches_screenshots_developer_rating(self):
        self._run_worker()
        db = GameDatabase(self.db_path)
        stored = db.get_game_details_by_igdb_id(IGDB_ID)
        db.close()
        self.assertEqual(stored.screenshot_urls, SCREENSHOTS)
        self.assertEqual(stored.developer, "Dev")
        self.assertEqual(stored.rating, 82)

    def test_second_fetch_comes_from_cache(self):
        self._run_worker()
        self.igdb.get_game_info.reset_mock()
        args = self._run_worker()
        self.igdb.get_game_info.assert_not_called()
        self.assertEqual(json.loads(args[6]), SCREENSHOTS)


if __name__ == "__main__":
    unittest.main()
