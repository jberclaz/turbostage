import os
import stat
import tempfile
import zipfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from turbostage import game_launcher
from turbostage.game_launcher import GameLauncher, build_dosbox_command, build_iso_autoexec


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


SETTING_KEYS = [
    "app/emulator_path",
    "app/games_path",
    "app/full_screen",
    "app/mt32_path",
    "app/soundcanvas_path",
    "app/disk_noise",
]


class QSettingsGuard:
    """Back up and restore TurboStage settings around a test."""

    def __init__(self, **values):
        self._values = values
        self._settings = QSettings("jberclaz", "TurboStage")
        self._backup = {}

    def __enter__(self):
        for key in SETTING_KEYS:
            self._backup[key] = self._settings.value(key, None)
        for key, value in self._values.items():
            self._settings.setValue(key, value)
        return self

    def __exit__(self, *args):
        for key, value in self._backup.items():
            if value is None:
                self._settings.remove(key)
            else:
                self._settings.setValue(key, value)


class StubDB:
    def __init__(self, archive_type="zip"):
        self._archive_type = archive_type

    def get_version_by_version_id(self, version_id):
        return SimpleNamespace(
            executable="GAME.EXE",
            archive="test.zip",
            config="",
            cycles=0,
            midi_device=0,
            version_id=version_id,
        )

    def get_archive_type(self, version_id):
        return self._archive_type

    def get_installation_status(self, version_id):
        return False, None

    def get_config_files_with_content(self, version_id, file_type):
        return []


def _make_fake_dosbox(script_body):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "dosbox")
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + script_body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return tmp, path


def _make_games_dir():
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(os.path.join(tmp, "test.zip"), "w") as zf:
        zf.writestr("GAME.EXE", b"fake exe")
    return tmp


class TestBuildDosboxCommand(TestCase):
    def test_minimal(self):
        self.assertEqual(build_dosbox_command("/bin/dosbox"), ["/bin/dosbox", "--noprimaryconf"])

    def test_full(self):
        self.assertEqual(
            build_dosbox_command("/bin/dosbox", "/base.conf", True, "/extra.conf"),
            ["/bin/dosbox", "--noprimaryconf", "--conf", "/base.conf", "--fullscreen", "--conf", "/extra.conf"],
        )


class TestBuildIsoAutoexec(TestCase):
    def test_installed_game_uses_c_drive(self):
        commands = build_iso_autoexec("/installs/7", "/games/test.iso", "GAME/GAME.EXE", True)
        self.assertEqual(
            commands,
            ['mount c "/installs/7"', 'imgmount d "/games/test.iso" -t iso', "c:", "cd GAME", "GAME.EXE"],
        )

    def test_disc_game_uses_d_drive(self):
        commands = build_iso_autoexec("/tmp/xyz", "/games/test.iso", "GAME.EXE", False)
        self.assertIn("d:", commands)
        self.assertNotIn("c:", commands[2:])

    def test_normalizes_iso_paths(self):
        commands = build_iso_autoexec("/tmp/xyz", "/games/test.iso", "/GAME/GAME.EXE;1", False)
        self.assertIn("cd GAME", commands)
        self.assertIn("GAME.EXE", commands)

    def test_non_iso_uses_cdrom_mount(self):
        commands = build_iso_autoexec("/tmp/xyz", "/games/game.cue", "GAME.EXE", False)
        self.assertTrue(any("cdrom" in c for c in commands))


class TestGameLauncherProcess(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def _run_until_finished(self, launcher, timeout_ms=15000):
        loop = QEventLoop()
        result = {}
        failsafe = QTimer()
        failsafe.setSingleShot(True)
        failsafe.timeout.connect(loop.quit)
        failsafe.start(timeout_ms)
        launcher.finished.connect(lambda completed, path: (result.setdefault("args", (completed, path)), loop.quit()))
        loop.exec()
        failsafe.stop()
        self.assertIn("args", result, "finished signal was not emitted in time")
        return result["args"]

    def test_launch_and_stop(self):
        bundle_dir, fake_dosbox = _make_fake_dosbox("sleep 30")
        games_dir = _make_games_dir()
        try:
            with QSettingsGuard(
                **{
                    "app/emulator_path": fake_dosbox,
                    "app/games_path": games_dir,
                    "app/full_screen": False,
                    "app/mt32_path": "",
                    "app/soundcanvas_path": "",
                    "app/disk_noise": False,
                }
            ):
                launcher = GameLauncher(track_change=True)
                try:
                    self.assertTrue(launcher.launch_game(7, StubDB()))
                    self.assertTrue(launcher.is_running)
                    temp_dir = launcher._temp_dir
                    self.assertTrue(temp_dir and os.path.isdir(temp_dir))
                    QTimer.singleShot(500, launcher.stop)
                    completed, path = self._run_until_finished(launcher)
                    self.assertFalse(completed)
                    self.assertIsNone(path)
                    self.assertFalse(launcher.is_running)
                    self.assertFalse(os.path.exists(temp_dir), "temp dir should be cleaned up")
                finally:
                    launcher.deleteLater()
        finally:
            import shutil

            shutil.rmtree(bundle_dir, ignore_errors=True)
            shutil.rmtree(games_dir, ignore_errors=True)

    def test_crash_reports_warning(self):
        _, fake_dosbox = _make_fake_dosbox("exit 3")
        games_dir = _make_games_dir()
        try:
            with QSettingsGuard(
                **{
                    "app/emulator_path": fake_dosbox,
                    "app/games_path": games_dir,
                    "app/full_screen": False,
                    "app/mt32_path": "",
                    "app/soundcanvas_path": "",
                    "app/disk_noise": False,
                }
            ):
                launcher = GameLauncher()
                try:
                    with patch.object(game_launcher.QMessageBox, "warning") as mock_warning:
                        self.assertTrue(launcher.launch_game(7, StubDB()))
                        completed, _ = self._run_until_finished(launcher)
                        self.assertFalse(completed)
                        mock_warning.assert_called_once()
                finally:
                    launcher.deleteLater()
        finally:
            import shutil

            shutil.rmtree(os.path.dirname(fake_dosbox), ignore_errors=True)
            shutil.rmtree(games_dir, ignore_errors=True)

    def test_double_launch_rejected(self):
        _, fake_dosbox = _make_fake_dosbox("sleep 30")
        games_dir = _make_games_dir()
        try:
            with QSettingsGuard(
                **{
                    "app/emulator_path": fake_dosbox,
                    "app/games_path": games_dir,
                    "app/full_screen": False,
                    "app/mt32_path": "",
                    "app/soundcanvas_path": "",
                    "app/disk_noise": False,
                }
            ):
                launcher = GameLauncher()
                try:
                    self.assertTrue(launcher.launch_game(7, StubDB()))
                    self.assertFalse(launcher.launch_game(7, StubDB()))
                    launcher.stop()
                    self._run_until_finished(launcher)
                finally:
                    launcher.deleteLater()
        finally:
            import shutil

            shutil.rmtree(os.path.dirname(fake_dosbox), ignore_errors=True)
            shutil.rmtree(games_dir, ignore_errors=True)
