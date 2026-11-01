import os
from unittest import TestCase
from unittest.mock import MagicMock

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidget, QTableWidgetItem

from turbostage.db.game_database import LocalGameDetails
from turbostage.ui.game_grid_widget import GameGridWidget
from turbostage.ui.main_window import MainWindow

DETAILS = ("summary", "", "January 01, 1993", "Shooter", "id", "id", "[]", 80)


def _ensure_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeWorker(QObject):
    finished = Signal(str, str, str, str, str, str, str, int)


def _bare_window():
    """A MainWindow without __init__: the real one opens the user's database and settings."""
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._game_info = MagicMock()
    window._current_fetch_worker = None
    return window


class TestStaleDetailsAreIgnored(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_only_the_current_request_reaches_the_panel(self):
        window = _bare_window()
        old, current = FakeWorker(), FakeWorker()
        for worker in (old, current):
            worker.finished.connect(window._on_game_info_fetched)
        window._current_fetch_worker = current

        old.finished.emit(*DETAILS)  # the previous selection's details arrive late
        window._game_info.set_game_info.assert_not_called()

        current.finished.emit(*DETAILS)
        window._game_info.set_game_info.assert_called_once_with(*DETAILS)
        window.deleteLater()

    def test_nothing_applies_after_deselecting(self):
        window = _bare_window()
        worker = FakeWorker()
        worker.finished.connect(window._on_game_info_fetched)
        window._current_fetch_worker = worker
        window._current_fetch_worker = None  # what on_game_change does on any selection change

        worker.finished.emit(*DETAILS)
        window._game_info.set_game_info.assert_not_called()
        window.deleteLater()


class TestSelectVersion(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_selects_the_version_in_both_views(self):
        window = _bare_window()
        window.game_table = QTableWidget(3, 4)
        window.game_grid = GameGridWidget()
        games = []
        for row, version_id in enumerate((11, 22, 33)):
            item = QTableWidgetItem(f"Game {version_id}")
            item.setData(Qt.UserRole, (version_id, version_id, False, False))
            window.game_table.setItem(row, 0, item)
            games.append(
                (LocalGameDetails(version_id, f"Game {version_id}", 0, "", "default", version_id), False, False)
            )
        window.game_grid.set_games(games)

        self.assertTrue(window._select_version(22))
        self.assertEqual(window.game_table.selectedItems()[0].text(), "Game 22")
        self.assertEqual(window.game_grid.currentItem().text(), "Game 22")
        self.assertFalse(window._select_version(99))
        window.deleteLater()
