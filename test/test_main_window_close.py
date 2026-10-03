import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from turbostage.ui.main_window import MainWindow


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def _bare_window(launcher):
    """A MainWindow without __init__: the real one opens the user's database and settings."""
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.status = window.statusBar()
    window._play_timer = QTimer(window)
    window._play_title = "Doom"
    window._launcher = launcher
    window._quit_after_game = False
    window._gamedb = MagicMock()
    window._set_library_locked = MagicMock()
    window.on_game_change = MagicMock()
    window.load_games = MagicMock()
    return window


def _running_launcher():
    launcher = MagicMock()
    launcher.is_running = True
    launcher.new_files = {"DOOMSAV0.DSG": b"save"}
    launcher.modified_files = {}
    launcher.version_id = 42
    return launcher


class TestCloseWhileGameRunning(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def test_declining_keeps_game_and_window(self):
        launcher = _running_launcher()
        window = _bare_window(launcher)
        window.show()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.assertFalse(window.close())
        launcher.stop.assert_not_called()
        self.assertTrue(window.isVisible())
        window.deleteLater()

    def test_quit_stops_game_saves_files_then_closes(self):
        launcher = _running_launcher()
        window = _bare_window(launcher)
        window.show()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question:
            self.assertFalse(window.close())  # deferred until the game has exited
            self.assertFalse(window.close())  # a second close while stopping does not re-prompt
        question.assert_called_once()
        launcher.stop.assert_called_once()
        self.assertTrue(window.isVisible())

        # DOSBox exits: the normal finished handler stores the save, then closes.
        launcher.is_running = False
        window._on_game_finished(False, None, False, launcher)
        window._gamedb.add_extra_files.assert_called_once()
        self.assertEqual(window._gamedb.add_extra_files.call_args.args[0], {"DOOMSAV0.DSG": b"save"})
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        window.deleteLater()

    def test_close_without_game_closes_immediately(self):
        window = _bare_window(None)
        window.show()
        self.assertTrue(window.close())
        window.deleteLater()
