import os
from unittest import TestCase

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from turbostage.db.game_database import LocalGameDetails
from turbostage.ui.game_grid_widget import (
    BADGE_DOWNLOAD,
    BADGE_INSTALL,
    COVER_HEIGHT,
    COVER_WIDTH,
    GameGridWidget,
    badge_for_item,
)
from turbostage.ui.main_window import sort_games


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def _game(title, release_date=0, genre="", version_id=1, **kwargs):
    return LocalGameDetails(
        igdb_id=version_id,
        title=title,
        release_date=release_date,
        genre=genre,
        version="default",
        version_id=version_id,
        **kwargs,
    )


class TestBadgeForItem(TestCase):
    def test_ready_game_has_no_badge(self):
        self.assertIsNone(badge_for_item(False, False))

    def test_downloadable_badge(self):
        self.assertEqual(badge_for_item(False, True), BADGE_DOWNLOAD)

    def test_install_badge(self):
        self.assertEqual(badge_for_item(True, False), BADGE_INSTALL)

    def test_download_wins_over_install(self):
        self.assertEqual(badge_for_item(True, True), BADGE_DOWNLOAD)


class TestGameGridWidget(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_placeholder_has_cover_size(self):
        pixmap = GameGridWidget._make_placeholder("Doom")
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), COVER_WIDTH)
        self.assertEqual(pixmap.height(), COVER_HEIGHT)

    def test_placeholder_handles_empty_title(self):
        pixmap = GameGridWidget._make_placeholder("")
        self.assertFalse(pixmap.isNull())

    def test_status_tooltips(self):
        grid = GameGridWidget()
        try:
            grid.set_games(
                [
                    (_game("Ready", version_id=1), False, False),
                    (_game("ToInstall", version_id=2), True, False),
                    (_game("ToDownload", version_id=3), False, True),
                ]
            )
            self.assertEqual(grid.item(0).toolTip(), "Ready")
            self.assertIn("install", grid.item(1).toolTip().lower())
            self.assertIn("download", grid.item(2).toolTip().lower())
            for i in range(3):
                self.assertFalse(grid.item(i).icon().isNull())
        finally:
            grid.deleteLater()


class TestSortGames(TestCase):
    def test_sort_by_title(self):
        games = [_game("Zork"), _game("doom"), _game("Aladdin")]
        self.assertEqual([g.title for g in sort_games(games, "title")], ["Aladdin", "doom", "Zork"])

    def test_sort_by_genre(self):
        games = [_game("A", genre="Shooter"), _game("B", genre="adventure"), _game("C", genre="RPG")]
        self.assertEqual([g.title for g in sort_games(games, "genre")], ["B", "C", "A"])

    def test_sort_by_release_date_newest_first(self):
        games = [_game("Old", release_date=100), _game("New", release_date=300), _game("Mid", release_date=200)]
        self.assertEqual([g.title for g in sort_games(games, "release_date")], ["New", "Mid", "Old"])

    def test_unknown_sort_defaults_to_title(self):
        games = [_game("B"), _game("A")]
        self.assertEqual([g.title for g in sort_games(games, "bogus")], ["A", "B"])
