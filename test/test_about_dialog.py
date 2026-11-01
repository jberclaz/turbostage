import os
from unittest import TestCase
from unittest.mock import MagicMock, PropertyMock

from PySide6.QtWidgets import QApplication, QLabel

from turbostage import __version__
from turbostage.game_metadata import MetadataUnavailable
from turbostage.ui.about_dialog import AboutDialog


class TestAboutDialog(TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._app = QApplication.instance() or QApplication([])

    def _text(self, metadata):
        dialog = AboutDialog(metadata)
        try:
            return " ".join(label.text() for label in dialog.findChildren(QLabel))
        finally:
            dialog.deleteLater()

    def test_credits_igdb_with_link_and_snapshot_date(self):
        metadata = MagicMock()
        type(metadata).generated_at = PropertyMock(return_value="2026-11-01")
        text = self._text(metadata)
        self.assertIn("https://www.igdb.com", text)
        self.assertIn("IGDB.com", text)
        self.assertIn("2026-11-01", text)
        self.assertIn(__version__, text)

    def test_unreadable_catalog_still_shows_attribution(self):
        metadata = MagicMock()
        type(metadata).generated_at = PropertyMock(side_effect=MetadataUnavailable("corrupt"))
        text = self._text(metadata)
        self.assertIn("IGDB.com", text)
        self.assertNotIn("snapshot", text)
