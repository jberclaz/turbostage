"""Games added from an unpacked folder instead of a zip or ISO archive."""

import os
import shutil
import tempfile
import unittest
import zipfile
from test.test_game_launcher import QSettingsGuard, StubDB, _make_fake_dosbox
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from turbostage import iso_utils, utils
from turbostage.add_game_worker import AddGameWorker, IdentifyArchiveWorker
from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase
from turbostage.game_launcher import GameLauncher
from turbostage.ui.game_setup_widget import GameSetupWidget
from turbostage.ui.main_window import list_local_games
from turbostage.ui.new_game_wizard import NewGameWizard

GAME_FILES = {
    "MK.EXE": b"MZ" + b"exe" * 400,
    "DATA/GAME.DAT": b"game data " * 300,
    "DATA/SOUND.DAT": b"sound data " * 200,
    "SETUP.COM": b"setup" * 10,
    "README.TXT": b"read me",
}


def _ensure_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _make_folder(path: str, files: dict[str, bytes]):
    for name, data in files.items():
        full = os.path.join(path, *name.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)


def _make_zip(path: str, files: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


class TestFolderHashing(unittest.TestCase):
    def setUp(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.dir = tempdir.name
        self.folder = os.path.join(self.dir, "mk")
        _make_folder(self.folder, GAME_FILES)
        self.zip = os.path.join(self.dir, "mk.zip")
        _make_zip(self.zip, GAME_FILES)

    def test_archive_type(self):
        self.assertEqual(iso_utils.get_archive_type(self.folder), "dir")
        self.assertEqual(iso_utils.get_archive_type(self.zip), "zip")

    def test_folder_hashes_match_zip_hashes(self):
        dir_type, dir_hashes = utils.hash_archive_top(self.folder, 4)
        zip_type, zip_hashes = utils.hash_archive_top(self.zip, 4)
        self.assertEqual(dir_type, "dir")
        self.assertEqual(zip_type, "zip")
        self.assertEqual(sorted(dir_hashes), sorted(zip_hashes))

    def test_executables_use_slash_paths(self):
        nested = os.path.join(self.folder, "BIN")
        _make_folder(nested, {"TOOL.BAT": b"@echo off"})
        self.assertEqual(utils.list_executables_in_dir(self.folder), ["BIN/TOOL.BAT", "MK.EXE", "SETUP.COM"])
        names = [h[0] for h in utils.hash_archive_executables(self.folder)]
        self.assertEqual(names, ["BIN/TOOL.BAT", "MK.EXE", "SETUP.COM"])

    def test_binary_outside_top_files_is_hashed(self):
        _, hashes = utils.hash_for_new_version(self.folder, "SETUP.COM", 2)
        by_name = {h[0]: h[2] for h in hashes}
        self.assertEqual(by_name["SETUP.COM"], utils.compute_file_md5(os.path.join(self.folder, "SETUP.COM")))

    def test_missing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            utils.compute_hash_for_largest_files_in_dir(os.path.join(self.dir, "missing"))

    def test_wizard_and_setup_panel_list_folder_executables(self):
        expected = ["MK.EXE", "SETUP.COM"]
        self.assertEqual(NewGameWizard.get_executables_from_archive(self.folder), expected)
        self.assertEqual(GameSetupWidget._list_binaries(self.folder), expected)


class TestListLocalGames(unittest.TestCase):
    def test_lists_archives_and_folders(self):
        with tempfile.TemporaryDirectory() as games:
            for name in ("a.zip", "b.ISO", "notes.txt"):
                open(os.path.join(games, name), "wb").close()
            os.mkdir(os.path.join(games, "Doom"))
            os.mkdir(os.path.join(games, ".hidden"))
            self.assertEqual(list_local_games(games), ["Doom", "a.zip", "b.ISO"])


class TestAddAndIdentifyFolder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def setUp(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.dir = tempdir.name
        self.db_path = os.path.join(self.dir, "test.db")
        DatabaseManager.initialize_database(self.db_path)
        self.metadata = MagicMock()
        self.metadata.get_game_info.return_value = None

    def _identify(self, path):
        worker = IdentifyArchiveWorker(path, self.db_path)
        identified, failed = [], []
        worker.signals.identified.connect(lambda *args: identified.append(args))
        worker.signals.failed.connect(lambda *args: failed.append(args))
        worker.run()
        self.assertEqual(failed, [])
        return identified

    def test_new_folder_game_is_added_as_dir(self):
        folder = os.path.join(self.dir, "mk")
        _make_folder(folder, GAME_FILES)
        AddGameWorker("Mortal Kombat", "vga", 1618, folder, "MK.EXE", None, 0, "", self.db_path, self.metadata).run()
        db = GameDatabase(self.db_path)
        try:
            versions = db.get_all_game_versions(1618, True)
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0].archive, "mk")
            self.assertEqual(db.get_archive_type(versions[0].version_id), "dir")
        finally:
            db.close()

    def test_folder_matches_version_added_from_zip(self):
        known = os.path.join(self.dir, "mk.zip")
        _make_zip(known, {f"MK/{name}": data for name, data in GAME_FILES.items()})
        AddGameWorker("Mortal Kombat", "vga", 1618, known, "MK/MK.EXE", None, 0, "", self.db_path, self.metadata).run()

        folder = os.path.join(self.dir, "Mortal Kombat")
        _make_folder(folder, GAME_FILES)
        identified = self._identify(folder)
        self.assertEqual(len(identified), 1)
        _, match = identified[0]
        self.assertIsNotNone(match)
        self.assertEqual(match.archive_type, "dir")
        self.assertEqual(match.executable, "MK.EXE")

    def test_unknown_folder_reports_no_match(self):
        folder = os.path.join(self.dir, "other")
        _make_folder(folder, {"A.EXE": b"a" * 100, "B.DAT": b"b" * 200})
        self.assertEqual(self._identify(folder), [(folder, None)])


class FolderStubDB(StubDB):
    def __init__(self, extra_files=None):
        super().__init__(archive_type="dir")
        self.extra_files = extra_files or []

    def get_version_by_version_id(self, version_id):
        return SimpleNamespace(
            executable="GAME/GAME.EXE",
            archive="mygame",
            config="",
            cycles=0,
            midi_device=0,
            version_id=version_id,
        )

    def get_config_files_with_content(self, version_id, file_type):
        return self.extra_files


# Writes a save file next to the executable DOSBox is given (its last argument).
SAVING_DOSBOX = 'for a; do last="$a"; done\necho saved > "$(dirname "$last")/SAVE.DAT"'


class TestLaunchFolderGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def setUp(self):
        self.bundle_dir, self.fake_dosbox = _make_fake_dosbox(SAVING_DOSBOX)
        self.addCleanup(shutil.rmtree, self.bundle_dir, True)
        self.games_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.games_dir, True)
        self.game_dir = os.path.join(self.games_dir, "mygame")
        _make_folder(self.game_dir, {"GAME/GAME.EXE": b"fake exe", "GAME/OPTIONS.CFG": b"original"})

    def _settings(self):
        return QSettingsGuard(
            **{
                "app/emulator_path": self.fake_dosbox,
                "app/games_path": self.games_dir,
                "app/full_screen": False,
                "app/mt32_path": "",
                "app/soundcanvas_path": "",
                "app/disk_noise": False,
            }
        )

    def _run(self, launcher, db):
        loop = QEventLoop()
        done = []
        failsafe = QTimer()
        failsafe.setSingleShot(True)
        failsafe.timeout.connect(loop.quit)
        failsafe.start(15000)
        launcher.finished.connect(lambda *args: (done.append(args), loop.quit()))
        # The fake DOSBox exits at once, which would show a modal warning.
        warn = unittest.mock.patch.object(GameLauncher, "_warn_immediate_exit")
        warn.start()
        self.addCleanup(warn.stop)
        self.assertTrue(launcher.launch_game(3, db))
        self.assertIsNone(launcher._temp_dir, "a game folder must not be copied")
        loop.exec()
        failsafe.stop()
        self.assertTrue(done, "finished signal was not emitted in time")

    def test_runs_in_place_and_keeps_folder(self):
        # A stale config stored in the database must not overwrite the folder's own.
        db = FolderStubDB(extra_files=[("GAME/OPTIONS.CFG", b"from database")])
        with self._settings():
            launcher = GameLauncher(track_change=False)
            try:
                self._run(launcher, db)
            finally:
                launcher.deleteLater()
        self.assertTrue(os.path.isfile(os.path.join(self.game_dir, "GAME", "GAME.EXE")))
        self.assertTrue(os.path.isfile(os.path.join(self.game_dir, "GAME", "SAVE.DAT")))
        with open(os.path.join(self.game_dir, "GAME", "OPTIONS.CFG"), "rb") as f:
            self.assertEqual(f.read(), b"original")
        self.assertEqual(launcher.new_files, {})

    def test_tracking_reports_files_written_in_folder(self):
        with self._settings():
            launcher = GameLauncher(track_change=True)
            try:
                self._run(launcher, FolderStubDB())
            finally:
                launcher.deleteLater()
        self.assertEqual(set(launcher.new_files), {os.path.join("GAME", "SAVE.DAT")})
        self.assertTrue(os.path.isdir(self.game_dir))

    def test_missing_executable_is_reported(self):
        os.remove(os.path.join(self.game_dir, "GAME", "GAME.EXE"))
        with self._settings():
            launcher = GameLauncher()
            try:
                with unittest.mock.patch("turbostage.game_launcher.QMessageBox.warning") as warning:
                    self.assertFalse(launcher.launch_game(3, FolderStubDB()))
                self.assertIn("GAME/GAME.EXE", warning.call_args.args[2])
            finally:
                launcher.deleteLater()
        self.assertTrue(os.path.isdir(self.game_dir))


if __name__ == "__main__":
    unittest.main()
