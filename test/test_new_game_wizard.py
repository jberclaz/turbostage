from unittest import TestCase

from turbostage.ui.new_game_wizard import GameTitlePage


class TestSanitizeSearchQueries(TestCase):
    def _first(self, name: str) -> str:
        return GameTitlePage._sanitize_search_queries(name)[0]

    def test_strips_scene_tags_and_version(self):
        self.assertEqual(self._first("Prince-of-Persia_DOS_EN_v14"), "Prince of Persia")

    def test_strips_release_year(self):
        self.assertEqual(self._first("Screamer_1995"), "Screamer")

    def test_keeps_sequel_number(self):
        self.assertEqual(self._first("Screamer_2_1996"), "Screamer 2")

    def test_strips_dotted_version(self):
        self.assertEqual(self._first("doom_v1.9"), "doom")

    def test_preserves_model_number_hyphens(self):
        self.assertEqual(self._first("F-15-Strike-Eagle-III_DOS_EN"), "F-15 Strike Eagle III")
        self.assertEqual(self._first("A-10-Tank-Killer-v-15_DOS_EN"), "A-10 Tank Killer")

    def test_splits_camelcase_and_roman_numeral(self):
        self.assertEqual(self._first("WingCommanderIII-CD1of4"), "Wing Commander III")

    def test_keeps_camelcase_brand_name_as_fallback(self):
        self.assertIn("SimCity", GameTitlePage._sanitize_search_queries("SimCity_DOS_EN_v110"))

    def test_strips_disc_numbers(self):
        self.assertEqual(self._first("screamer201"), "screamer")
        self.assertEqual(self._first("screamer01"), "screamer")

    def test_strips_publisher_and_allcaps_duplicate(self):
        self.assertEqual(self._first("Star.Wars.Dark.Forces.1995.Lucas.Arts.DARK_FORCES"), "Star Wars Dark Forces")

    def test_keeps_meaningful_allcaps_token(self):
        self.assertEqual(self._first("Arkanoid-Revenge-of-DOH_DOS_EN"), "Arkanoid Revenge of DOH")
