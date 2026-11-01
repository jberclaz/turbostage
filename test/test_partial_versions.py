import os
from unittest import TestCase

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from turbostage.db.game_database import LocalGameDetails
from turbostage.ui.game_grid_widget import COVER_HEIGHT, COVER_WIDTH, VERSION_ROLE, GameGridWidget
from turbostage.ui.game_info_widget import GameInfoWidget
from turbostage.version_labels import display_title, partial_version_label, partial_version_note


def _ensure_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _game(title, version, version_id):
    return LocalGameDetails(
        igdb_id=version_id, title=title, release_date=0, genre="", version=version, version_id=version_id
    )


class TestPartialVersionLabel(TestCase):
    def test_demo_and_shareware_names(self):
        for name, label in (
            ("demo", "Demo"),
            ("Demo", "Demo"),
            ("playable demo", "Demo"),
            ("shareware", "Shareware"),
            ("Shareware 1.4", "Shareware"),
        ):
            self.assertEqual(partial_version_label(name), label, name)

    def test_full_versions_are_not_partial(self):
        for name in ("default", "freeware", "cdrom", "vga", "fr", "", None, "demolition", "demos2"):
            self.assertIsNone(partial_version_label(name), name)

    def test_note_only_for_partial_versions(self):
        self.assertIn("not the complete game", partial_version_note("demo"))
        self.assertIn("not the complete version", partial_version_note("shareware"))
        self.assertIsNone(partial_version_note("default"))

    def test_display_title(self):
        self.assertEqual(display_title("Doom", "shareware"), "Doom (Shareware)")
        self.assertEqual(display_title("Prince of Persia", "demo"), "Prince of Persia (Demo)")
        self.assertEqual(display_title("Doom", "default"), "Doom")
        self.assertEqual(display_title(None, "demo"), "Unknown (Demo)")


class TestGridShowsPartialVersions(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_full_game_and_demo_side_by_side(self):
        grid = GameGridWidget()
        try:
            grid.set_games(
                [
                    (_game("Prince of Persia", "default", 1), False, False),
                    (_game("Prince of Persia", "demo", 2), False, True),
                ]
            )
            full, demo = grid.item(0), grid.item(1)
            self.assertEqual(full.text(), "Prince of Persia")
            self.assertEqual(demo.text(), "Prince of Persia (Demo)")
            self.assertEqual(demo.data(VERSION_ROLE), "demo")
            self.assertNotIn("not the complete", full.toolTip())
            self.assertIn("download", demo.toolTip().lower())
            self.assertIn("not the complete game", demo.toolTip())
        finally:
            grid.deleteLater()

    def test_partial_badge_is_drawn_at_the_top(self):
        cover = QPixmap(COVER_WIDTH, COVER_HEIGHT)
        cover.fill(QColor("white"))
        badged = GameGridWidget._add_badge(cover, "Demo", top=True).toImage()
        self.assertNotEqual(badged.pixelColor(12, 12), QColor("white"))  # top-left pill
        self.assertEqual(badged.pixelColor(12, COVER_HEIGHT - 12), QColor("white"))  # bottom untouched


class TestInfoPanelVersionNote(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_note_survives_details_arriving(self):
        widget = GameInfoWidget()
        try:
            widget.set_version_note(partial_version_note("shareware"))
            self.assertTrue(widget.version_note_label.isVisibleTo(widget))
            # Game details load in the background and reset the panel.
            widget.set_game_info("summary", "", "January 01, 1993", "Shooter", "id", "id", "[]", 80)
            self.assertTrue(widget.version_note_label.isVisibleTo(widget))
            self.assertIn("Shareware", widget.version_note_label.text())

            widget.set_version_note(None)
            self.assertFalse(widget.version_note_label.isVisibleTo(widget))
        finally:
            widget.deleteLater()
