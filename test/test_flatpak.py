from unittest import TestCase
from unittest.mock import MagicMock, patch

from turbostage import utils


class TestFlatpakDefaults(TestCase):
    def test_sandbox_uses_bundled_dosbox(self):
        settings = MagicMock()
        with patch("turbostage.utils.os.path.exists", return_value=True):
            self.assertTrue(utils.is_flatpak())
            utils.apply_flatpak_defaults(settings)
        settings.setValue.assert_called_once_with("app/emulator_path", "/app/bin/dosbox")

    def test_outside_sandbox_settings_are_untouched(self):
        settings = MagicMock()
        with patch("turbostage.utils.os.path.exists", return_value=False):
            self.assertFalse(utils.is_flatpak())
            utils.apply_flatpak_defaults(settings)
        settings.setValue.assert_not_called()
