import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from unittest import TestCase
from unittest.mock import patch

from turbostage import app_paths, log_setup
from turbostage.data_migration import migrate_legacy_data


class FakeSettings:
    def __init__(self, **values):
        self.values = dict(values)

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


def _write(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _make_db(path, install_paths=()):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE games (igdb_id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO games VALUES (673, 'Doom')")
    conn.execute("CREATE TABLE installations (version_id INTEGER PRIMARY KEY, install_path TEXT NOT NULL)")
    conn.executemany("INSERT INTO installations VALUES (?, ?)", list(enumerate(install_paths, start=1)))
    conn.commit()
    return conn


class TestMigrateLegacyData(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.target = os.path.join(self.root, "TurboStage")

    def r(self, *parts):
        return os.path.join(self.root, *parts)

    def t(self, *parts):
        return os.path.join(self.target, *parts)

    def migrate(self, settings):
        return migrate_legacy_data(settings, root=self.root, target=self.target)

    def test_moves_everything_and_rewrites_references(self):
        conn = _make_db(self.r("turbostage.db"), [self.r("installs", "12")])
        conn.close()
        for name in ("turbostage.log", "turbostage.log.1", "dosbox.log"):
            _write(self.r(name))
        _write(self.r("image_cache", "covers", "abc.jpg"))
        _write(self.r("dosbox", "dosbox-staging-0.83", "dosbox"))
        _write(self.r("mt32_roms", "MT32_CONTROL.ROM"))
        _write(self.r("soundcanvas_roms", "SC-55", "rom.bin"))
        _write(self.r("installs", "12", "GAME", "PLAY.EXE"))
        settings = FakeSettings(
            **{
                "app/emulator_path": self.r("dosbox", "dosbox-staging-0.83", "dosbox"),
                "app/mt32_path": self.r("mt32_roms"),
                "app/soundcanvas_path": self.r("soundcanvas_roms", "SC-55"),
                "app/games_path": "/home/user/games",
            }
        )

        result = self.migrate(settings)

        self.assertTrue(result.use_new_folder)
        self.assertEqual(result.warnings, [])
        for name in ("turbostage.db", "turbostage.log", "turbostage.log.1", "dosbox.log"):
            self.assertTrue(os.path.isfile(self.t(name)), name)
            self.assertFalse(os.path.exists(self.r(name)), name)
        for path in ("image_cache/covers/abc.jpg", "mt32_roms/MT32_CONTROL.ROM", "installs/12/GAME/PLAY.EXE"):
            self.assertTrue(os.path.isfile(self.t(path)), path)
        self.assertEqual(settings.values["app/emulator_path"], self.t("dosbox", "dosbox-staging-0.83", "dosbox"))
        self.assertEqual(settings.values["app/mt32_path"], self.t("mt32_roms"))
        self.assertEqual(settings.values["app/soundcanvas_path"], self.t("soundcanvas_roms", "SC-55"))
        self.assertEqual(settings.values["app/games_path"], "/home/user/games")  # the user's own folder
        conn = sqlite3.connect(self.t("turbostage.db"))
        self.assertEqual(conn.execute("SELECT title FROM games").fetchone(), ("Doom",))
        self.assertEqual(conn.execute("SELECT install_path FROM installations").fetchone(), (self.t("installs", "12"),))
        conn.close()

    def test_unsaved_wal_changes_are_kept(self):
        # A connection still open: the latest changes are only in the -wal side file.
        conn = _make_db(self.r("turbostage.db"))
        conn.execute("INSERT INTO games VALUES (284, 'Wolfenstein 3D')")
        conn.commit()
        self.assertTrue(os.path.getsize(self.r("turbostage.db-wal")) > 0)
        result = self.migrate(FakeSettings())
        conn.close()
        self.assertTrue(result.use_new_folder)
        titles = sqlite3.connect(self.t("turbostage.db")).execute("SELECT title FROM games ORDER BY igdb_id").fetchall()
        self.assertEqual(titles, [("Wolfenstein 3D",), ("Doom",)])

    def test_folders_of_other_programs_stay(self):
        _make_db(self.r("turbostage.db")).close()
        _write(self.r("dosbox", "their-file"))  # not referenced by our settings
        _write(self.r("image_cache", "thumbs", "x.png"))  # not our cache layout
        _write(self.r("installs", "someapp", "x"))  # not numbered, not referenced
        settings = FakeSettings(**{"app/emulator_path": "/usr/bin/dosbox"})
        self.migrate(settings)
        for path in ("dosbox/their-file", "image_cache/thumbs/x.png", "installs/someapp/x"):
            self.assertTrue(os.path.isfile(self.r(path)), path)
        self.assertEqual(settings.values["app/emulator_path"], "/usr/bin/dosbox")

    def test_nothing_is_overwritten(self):
        _make_db(self.r("turbostage.db")).close()
        _write(self.r("turbostage.log"), "old")
        _write(self.t("turbostage.log"), "new")
        result = self.migrate(FakeSettings())
        with open(self.t("turbostage.log")) as f:
            self.assertEqual(f.read(), "new")
        with open(self.r("turbostage.log")) as f:
            self.assertEqual(f.read(), "old")
        self.assertTrue(any("already exists" in w for w in result.warnings))

    def test_database_that_cannot_move_keeps_the_old_location(self):
        _make_db(self.r("turbostage.db")).close()
        _write(self.r("turbostage.log"))
        real_rename = os.rename

        def failing_rename(src, dst):
            if src.endswith("turbostage.db"):
                raise PermissionError("in use by another program")
            return real_rename(src, dst)

        with patch("turbostage.data_migration.os.rename", failing_rename):
            result = self.migrate(FakeSettings())
        self.assertFalse(result.use_new_folder)
        self.assertTrue(os.path.isfile(self.r("turbostage.db")))
        self.assertTrue(os.path.isfile(self.r("turbostage.log")))  # nothing else moved either

    def test_fresh_install_and_second_run(self):
        result = self.migrate(FakeSettings())
        self.assertTrue(result.use_new_folder)
        self.assertEqual(result.moved, [])
        _make_db(self.r("turbostage.db")).close()
        self.assertEqual(self.migrate(FakeSettings()).moved, ["turbostage.db"])
        again = self.migrate(FakeSettings())
        self.assertEqual((again.moved, again.warnings, again.use_new_folder), ([], [], True))


class TestAppPaths(TestCase):
    def tearDown(self):
        app_paths.reset()

    def test_data_dir_is_a_turbostage_folder(self):
        self.assertEqual(os.path.basename(app_paths.data_dir()), "TurboStage")
        self.assertEqual(os.path.dirname(app_paths.data_dir()), app_paths.platform_data_root())

    def test_legacy_root_override(self):
        app_paths.use_legacy_root()
        self.assertEqual(app_paths.data_dir(), app_paths.platform_data_root())


class TestCrashTraces(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        root = logging.getLogger()
        self._handlers = list(root.handlers)
        self.addCleanup(self._restore_logging)

    def _restore_logging(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            if handler not in self._handlers:
                root.removeHandler(handler)
                handler.close()

    def test_native_crash_is_reported_in_the_next_log(self):
        # A real segfault in a child process, after logging was set up.
        script = textwrap.dedent(f"""
            import faulthandler
            from turbostage import log_setup
            log_setup.setup_logging({self.dir!r})
            faulthandler._sigsegv()
        """)
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, cwd=os.getcwd())
        self.assertNotEqual(proc.returncode, 0)
        with open(os.path.join(self.dir, log_setup.CRASH_FILE_NAME)) as f:
            self.assertIn("Segmentation fault", f.read())

        log_setup.setup_logging(self.dir)  # the next session
        with open(os.path.join(self.dir, log_setup.LOG_FILE_NAME)) as f:
            log = f.read()
        self.assertIn("The previous session crashed", log)
        self.assertIn("Segmentation fault", log)
        with open(os.path.join(self.dir, log_setup.CRASH_FILE_NAME)) as f:
            self.assertEqual(f.read(), "")  # reported once, then reset
