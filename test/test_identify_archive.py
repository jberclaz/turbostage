import os
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QMainWindow

from turbostage.add_game_worker import AddGameWorker, ArchiveMatch, IdentifyArchiveWorker
from turbostage.db.database_manager import DatabaseManager
from turbostage.ui.main_window import MainWindow


def _make_zip(path: str, files: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


GAME_FILES = {
    "MK/MK.EXE": b"MZ" + b"exe" * 400,
    "MK/GAME.DAT": b"game data " * 300,
    "MK/SOUND.DAT": b"sound data " * 200,
    "MK/START.BAT": b"@echo off\nMK.EXE\n",
}


class TestIdentifyArchiveWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.dir = tempdir.name
        self.db_path = os.path.join(self.dir, "test.db")
        DatabaseManager.initialize_database(self.db_path)

        # Register a known game version from an archive.
        known = os.path.join(self.dir, "mk.zip")
        _make_zip(known, GAME_FILES)
        igdb = MagicMock()
        igdb.get_game_info.return_value = None
        AddGameWorker("Mortal Kombat", "vga", 1618, known, "MK/MK.EXE", None, 0, "", self.db_path, igdb).run()

    def _identify(self, path):
        worker = IdentifyArchiveWorker(path, self.db_path)
        identified, failed = [], []
        worker.signals.identified.connect(lambda *args: identified.append(args))
        worker.signals.failed.connect(lambda *args: failed.append(args))
        worker.run()
        return identified, failed

    def test_known_archive_is_matched(self):
        # Same files, different archive name and folder layout.
        path = os.path.join(self.dir, "copy.zip")
        _make_zip(path, {name.replace("MK/", "GAMES/MK/"): data for name, data in GAME_FILES.items()})
        identified, failed = self._identify(path)
        self.assertEqual(failed, [])
        self.assertEqual(len(identified), 1)
        game_path, match = identified[0]
        self.assertEqual(game_path, path)
        self.assertIsNotNone(match)
        self.assertEqual(match.archive_type, "zip")
        self.assertEqual(match.executable, "GAMES/MK/MK.EXE")

    def test_unknown_archive_reports_no_match(self):
        path = os.path.join(self.dir, "other.zip")
        _make_zip(path, {"A.EXE": b"a" * 100, "B.DAT": b"b" * 200})
        identified, failed = self._identify(path)
        self.assertEqual(failed, [])
        self.assertEqual(identified, [(path, None)])

    def test_corrupt_archive_reports_failure(self):
        path = os.path.join(self.dir, "broken.zip")
        with open(path, "wb") as f:
            f.write(b"this is not a zip file")
        identified, failed = self._identify(path)
        self.assertEqual(identified, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][0], path)
        self.assertTrue(failed[0][1])


class TestAddGameHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        window = MainWindow.__new__(MainWindow)
        QMainWindow.__init__(window)
        window.status = window.statusBar()
        window._identify_dialog = MagicMock()
        window._gamedb = MagicMock()
        window._on_game_added = MagicMock()
        return window

    def test_failure_closes_dialog_and_reports(self):
        window = self._window()
        dialog = window._identify_dialog
        with patch("turbostage.ui.main_window.QMessageBox.critical") as critical:
            window._on_archive_identify_failed("/games/broken.zip", "File is not a zip file")
        dialog.close.assert_called_once()
        self.assertIsNone(window._identify_dialog)
        self.assertIn("broken.zip", critical.call_args.args[2])
        window._gamedb.add_local_game_version.assert_not_called()

    def test_match_adds_local_version(self):
        window = self._window()
        window._gamedb.add_local_game_version.return_value = 1
        match = ArchiveMatch(7, "zip", "MK/MK.EXE", None)
        with patch("turbostage.ui.main_window.QMessageBox.information"):
            window._on_archive_identified("/games/mk.zip", match)
        self.assertIsNone(window._identify_dialog)
        window._gamedb.add_local_game_version.assert_called_once_with(
            7, "mk.zip", executable="MK/MK.EXE", config_executable=None, archive_type="zip", requires_install=False
        )
        window._on_game_added.assert_called_once()


if __name__ == "__main__":
    unittest.main()
