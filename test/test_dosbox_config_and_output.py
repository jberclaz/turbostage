import io
import os
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from turbostage.game_launcher import GameLauncher


def _last_value(config: str, key: str) -> str:
    """The value DOSBox ends up using: the last occurrence of the setting."""
    values = [line.split("=", 1)[1].strip() for line in config.splitlines() if line.strip().startswith(key)]
    return values[-1]


class TestMidiDeviceOrder(TestCase):
    def _config(self, config_content, midi_device):
        out = io.StringIO()
        GameLauncher._write_custom_dosbox_config_file(
            out, config_content, "/roms/mt32", "/roms/sc55", False, 0, midi_device=midi_device
        )
        return out.getvalue()

    def test_setup_tab_choice_overrides_game_config(self):
        game_config = "[midi]\nmididevice = port\n"
        self.assertEqual(_last_value(self._config(game_config, 1), "mididevice"), "mt32")
        self.assertEqual(_last_value(self._config(game_config, 2), "mididevice"), "soundcanvas")

    def test_game_config_applies_when_no_device_chosen(self):
        self.assertEqual(_last_value(self._config("[midi]\nmididevice = port\n", 0), "mididevice"), "port")


class TestDosboxOutputCapture(TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._app = QApplication.instance() or QApplication([])

    def _run(self, log_path):
        process = QProcess()
        with patch("turbostage.game_launcher.dosbox_log_file_path", return_value=log_path):
            GameLauncher._redirect_output(process)
        process.start(sys.executable, ["-c", "import sys; print('to stdout'); print('to stderr', file=sys.stderr)"])
        self.assertTrue(process.waitForFinished(10_000))
        return process

    def test_stdout_and_stderr_go_to_the_log(self):
        with tempfile.TemporaryDirectory() as tempdir:
            log_path = os.path.join(tempdir, "logs", "dosbox.log")  # folder created on demand
            self._run(log_path)
            with open(log_path) as f:
                output = f.read()
        self.assertIn("to stdout", output)
        self.assertIn("to stderr", output)

    def test_each_run_replaces_the_previous_log(self):
        with tempfile.TemporaryDirectory() as tempdir:
            log_path = os.path.join(tempdir, "dosbox.log")
            with open(log_path, "w") as f:
                f.write("previous game run\n")
            self._run(log_path)
            with open(log_path) as f:
                self.assertNotIn("previous game run", f.read())

    def test_unwritable_log_does_not_prevent_starting(self):
        with tempfile.TemporaryDirectory() as tempdir:
            blocker = os.path.join(tempdir, "not-a-folder")
            with open(blocker, "w"):
                pass
            with self.assertLogs("turbostage.game_launcher", "WARNING"):
                process = self._run(os.path.join(blocker, "dosbox.log"))
        self.assertEqual(process.exitStatus(), QProcess.ExitStatus.NormalExit)
        self.assertEqual(process.exitCode(), 0)
