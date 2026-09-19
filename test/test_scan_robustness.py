import os
import tempfile
import threading
import time
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase, GameDetails
from turbostage.scanning_thread import ScanningThread
from turbostage.ui.game_setup_widget import GameSetupWidget


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def _make_db(path):
    DatabaseManager.initialize_database(path)
    return GameDatabase(path)


def _add_game(db, igdb_id, title="Test Game"):
    details = GameDetails(
        title=title,
        release_date=946684800,
        genre="Adventure",
        summary="summary",
        publisher="publisher",
        cover_url="",
        igdb_id=igdb_id,
        developer="developer",
        rating=0,
    )
    game_id = db.insert_game_with_details(title, details)
    version_id = db.insert_game_version(game_id, "default", "GAME.EXE", None, "", 0)
    return game_id, version_id


class TestSetGameGraceful(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_unknown_game_does_not_raise(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.close()
            try:
                db = _make_db(tmp.name)
                widget = GameSetupWidget()
                try:
                    widget.set_game(999999, db)  # must not raise
                    self.assertFalse(widget.save_button.isEnabled())
                    self.assertIsNone(widget.selected_binary)
                    self.assertTrue(widget.empty_label.isVisibleTo(widget))
                finally:
                    widget.deleteLater()
            finally:
                os.unlink(tmp.name)

    def test_known_game_still_loads(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.close()
            try:
                db = _make_db(tmp.name)
                _, version_id = _add_game(db, 12345)
                db.add_local_game_version(version_id, "game.zip")
                widget = GameSetupWidget()
                try:
                    widget.set_game(12345, db)
                    self.assertEqual(widget.version_id, version_id)
                finally:
                    widget.deleteLater()
            finally:
                os.unlink(tmp.name)


class TestReplaceLocalVersions(TestCase):
    def test_replace_swaps_contents(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.close()
            try:
                db = _make_db(tmp.name)
                _, v1 = _add_game(db, 111, "Game One")
                _, v2 = _add_game(db, 222, "Game Two")
                db.add_local_game_version(v1, "one.zip")
                db.add_local_game_version(v2, "two.zip")
                self.assertEqual(len(db.get_games_with_local_versions()), 2)

                db.replace_local_versions([(v2, "two.zip", "GAME.EXE", None, "zip", False)])
                remaining = db.get_games_with_local_versions()
                self.assertEqual(len(remaining), 1)
                self.assertEqual(remaining[0].version_id, v2)

                db.replace_local_versions([])
                self.assertEqual(db.get_games_with_local_versions(), [])
            finally:
                os.unlink(tmp.name)

    def test_replace_keeps_first_of_duplicate_versions(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.close()
            try:
                db = _make_db(tmp.name)
                _, v1 = _add_game(db, 111, "Game One")
                # Two archives matching the same version must not violate
                # the UNIQUE constraint; the first one wins.
                db.replace_local_versions(
                    [
                        (v1, "one.zip", "GAME.EXE", None, "zip", False),
                        (v1, "one_copy.zip", "GAME.EXE", None, "zip", False),
                    ]
                )
                remaining = db.get_games_with_local_versions()
                self.assertEqual(len(remaining), 1)
            finally:
                os.unlink(tmp.name)


class TestScanningThread(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def _run_sync(self, worker):
        """Run the worker body synchronously, collecting signal emissions."""
        seen = {"progress": [], "load_games": 0, "finished": [], "errors": []}
        worker.progress.connect(lambda v: seen["progress"].append(v))
        worker.load_games.connect(lambda: seen.__setitem__("load_games", seen["load_games"] + 1))
        worker.scan_finished.connect(lambda matched, unmatched: seen["finished"].append((matched, unmatched)))
        worker.scan_error.connect(lambda message: seen["errors"].append(message))
        worker.run()
        return seen

    def test_interrupted_scan_touches_nothing(self):
        app = _ensure_app()
        release = threading.Event()
        worker = ScanningThread(["a.zip", "b.zip"], "/fake.db", "/games")
        try:
            with (
                patch("turbostage.scanning_thread.GameDatabase") as mock_db_cls,
                patch("turbostage.scanning_thread.utils") as mock_utils,
            ):
                mock_db = MagicMock()
                mock_db_cls.return_value = mock_db

                def slow_hash(path, n=4):
                    if path.endswith("b.zip"):
                        release.wait(timeout=10)
                    return ("zip", [("G.EXE", 10, "hash1")])

                mock_utils.hash_archive_top.side_effect = slow_hash
                mock_utils.hash_archive_executables.return_value = []
                mock_db.find_game_by_hashes.return_value = 7
                mock_db.resolve_local_executables.return_value = ("G.EXE", None)
                mock_db.get_version_requires_install.return_value = False

                seen = {"progress": [], "load_games": 0, "finished": []}
                worker.progress.connect(lambda v: seen["progress"].append(v))
                worker.load_games.connect(lambda: seen.__setitem__("load_games", seen["load_games"] + 1))
                worker.scan_finished.connect(lambda matched, unmatched: seen["finished"].append((matched, unmatched)))
                worker.start()

                # Wait for the first file, then cancel while blocked on the second.
                deadline = time.monotonic() + 10
                while not seen["progress"] and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(0.01)
                self.assertTrue(seen["progress"], "worker never started")
                worker.requestInterruption()
                release.set()
                self.assertTrue(worker.wait(10000), "worker did not stop")

                mock_db.replace_local_versions.assert_not_called()
                self.assertEqual(seen["load_games"], 0)
                self.assertEqual(seen["finished"], [])
        finally:
            worker.deleteLater()

    def test_collects_matches_and_reports_unmatched(self):
        worker = ScanningThread(["found.zip", "mystery.iso"], "/fake.db", "/games")
        try:
            with (
                patch("turbostage.scanning_thread.GameDatabase") as mock_db_cls,
                patch("turbostage.scanning_thread.utils") as mock_utils,
            ):
                mock_db = MagicMock()
                mock_db_cls.return_value = mock_db
                mock_utils.hash_archive_top.side_effect = lambda p, n=4: (
                    ("iso", [("X.EXE", 10, "hash2")]) if p.endswith(".iso") else ("zip", [("G.EXE", 10, "hash1")])
                )
                mock_utils.hash_archive_executables.return_value = []
                mock_db.find_game_by_hashes.side_effect = lambda hs: (7 if "hash1" in hs else None)
                mock_db.resolve_local_executables.return_value = ("G.EXE", None)
                mock_db.get_version_requires_install.return_value = False

                seen = self._run_sync(worker)

                mock_db.replace_local_versions.assert_called_once_with([(7, "found.zip", "G.EXE", None, "zip", False)])
                self.assertEqual(seen["load_games"], 1)
                self.assertEqual(seen["finished"], [(1, ["mystery.iso"])])
                self.assertEqual(seen["errors"], [])
        finally:
            worker.deleteLater()

    def test_scan_failure_is_reported(self):
        worker = ScanningThread(["found.zip"], "/fake.db", "/games")
        try:
            with (
                patch("turbostage.scanning_thread.GameDatabase") as mock_db_cls,
                patch("turbostage.scanning_thread.utils") as mock_utils,
            ):
                mock_db = MagicMock()
                mock_db_cls.return_value = mock_db
                mock_utils.hash_archive_top.return_value = (
                    "zip",
                    [("G.EXE", 10, "hash1")],
                )
                mock_utils.hash_archive_executables.return_value = []
                mock_db.find_game_by_hashes.return_value = 7
                mock_db.resolve_local_executables.return_value = ("G.EXE", None)
                mock_db.get_version_requires_install.return_value = False
                mock_db.replace_local_versions.side_effect = RuntimeError("boom")

                seen = self._run_sync(worker)

                self.assertEqual(seen["load_games"], 0)
                self.assertEqual(seen["finished"], [])
                self.assertEqual(seen["errors"], ["boom"])
                mock_db.close.assert_called_once_with()
        finally:
            worker.deleteLater()


class TestCloseAllThreadSafety(TestCase):
    def test_close_from_foreign_thread_does_not_raise(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.close()
            try:
                _make_db(tmp.name)
                leaked = []

                def build_in_worker():
                    leaked.append(GameDatabase(tmp.name))

                worker = threading.Thread(target=build_in_worker)
                worker.start()
                worker.join()
                # The pool now holds a connection created in the worker
                # thread; closing from here must not raise.
                leaked[0].close()
            finally:
                os.unlink(tmp.name)
