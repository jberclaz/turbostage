import os
import tempfile
from unittest import TestCase

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from turbostage.ui.setup_wizard import SetupWizard, count_game_archives, is_setup_completed, validate_emulator


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


class TestSetupWizardHelpers(TestCase):
    def test_count_game_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(count_game_archives(tmp), 0)
            open(os.path.join(tmp, "doom.zip"), "w").close()
            open(os.path.join(tmp, "quake.ISO"), "w").close()
            open(os.path.join(tmp, "readme.txt"), "w").close()
            self.assertEqual(count_game_archives(tmp), 2)
        self.assertEqual(count_game_archives("/nonexistent-folder-xyz"), 0)
        self.assertEqual(count_game_archives(""), 0)

    def test_validate_emulator_empty_and_missing(self):
        ok, _ = validate_emulator("")
        self.assertFalse(ok)
        ok, _ = validate_emulator("/nonexistent/dosbox")
        self.assertFalse(ok)

    def test_is_setup_completed_flag(self):
        settings = QSettings("turbostage-test", "setup-wizard-test")
        settings.clear()
        self.assertFalse(is_setup_completed(settings))
        settings.setValue("app/setup_completed", True)
        self.assertTrue(is_setup_completed(settings))
        settings.clear()


class TestSetupWizardPages(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def _clear_paths(self):
        settings = QSettings("jberclaz", "TurboStage")
        old_emu = settings.value("app/emulator_path", "")
        old_games = settings.value("app/games_path", "")
        settings.setValue("app/emulator_path", "")
        settings.setValue("app/games_path", "")
        return settings, old_emu, old_games

    def _restore_paths(self, settings, old_emu, old_games):
        settings.setValue("app/emulator_path", old_emu)
        settings.setValue("app/games_path", old_games)

    def test_emulator_page_requires_path(self):
        settings, old_emu, old_games = self._clear_paths()
        try:
            wizard = SetupWizard()
            try:
                self.assertFalse(wizard._emulator_page.isComplete())
            finally:
                wizard.deleteLater()
        finally:
            self._restore_paths(settings, old_emu, old_games)

    def test_games_page_requires_existing_dir(self):
        settings, old_emu, old_games = self._clear_paths()
        try:
            wizard = SetupWizard()
            try:
                self.assertFalse(wizard._games_page.isComplete())
                with tempfile.TemporaryDirectory() as tmp:
                    wizard._games_page.path_field.setText(tmp)
                    self.assertTrue(wizard._games_page.isComplete())
            finally:
                wizard.deleteLater()
        finally:
            self._restore_paths(settings, old_emu, old_games)

    def test_finish_page_defaults(self):
        wizard = SetupWizard()
        try:
            self.assertTrue(wizard.do_update_db)
            self.assertTrue(wizard.do_scan)
        finally:
            wizard.deleteLater()
