import os
import threading
from unittest import TestCase
from unittest.mock import MagicMock

import requests
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

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


class TestGameTitlePageSearch(TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            cls._app = QApplication([])

    def _wait_for_search(self):
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()  # deliver the queued result signal

    def test_search_runs_off_the_ui_thread(self):
        threads = []
        client = MagicMock()
        client.search_games.side_effect = lambda q: threads.append(threading.current_thread()) or []
        page = GameTitlePage(client, "doom.zip")
        try:
            self._wait_for_search()
            self.assertTrue(threads)
            self.assertNotIn(threading.main_thread(), threads)
        finally:
            page.deleteLater()

    def test_auto_search_tries_variants_until_one_matches(self):
        client = MagicMock()
        client.search_games.side_effect = lambda q: (
            [{"name": "Wing Commander III", "id": 7}] if q == "WingCommanderIII" else []
        )
        page = GameTitlePage(client, "WingCommanderIII-CD1of4.zip")
        try:
            self._wait_for_search()
            self.assertEqual(client.search_games.call_count, 2)
            self.assertEqual(page.game_list_model.games, [("Wing Commander III", 7)])
            self.assertFalse(page.search_status_label.isVisibleTo(page))
        finally:
            page.deleteLater()

    def test_offline_search_shows_error_and_retry_works(self):
        client = MagicMock()
        client.search_games.side_effect = requests.exceptions.ConnectionError("offline")
        page = GameTitlePage(client, "WingCommanderIII-CD1of4.zip")
        try:
            self._wait_for_search()
            # Auto-search stops at the first network failure.
            client.search_games.assert_called_once()
            self.assertTrue(page.search_status_label.isVisibleTo(page))
            self.assertIn("Could not reach", page.search_status_label.text())
            self.assertEqual(page.game_list_model.rowCount(), 0)

            client.search_games.side_effect = None
            client.search_games.return_value = [{"name": "Doom", "id": 1}]
            page.game_name_search_query.setText("Doom")
            page._search_games_slot()
            self._wait_for_search()
            self.assertFalse(page.search_status_label.isVisibleTo(page))
            self.assertEqual(page.game_list_model.rowCount(), 1)
        finally:
            page.deleteLater()

    def test_results_of_superseded_search_are_ignored(self):
        client = MagicMock()
        client.search_games.return_value = [{"name": "Doom", "id": 1}]
        page = GameTitlePage(client, "doom.zip")
        try:
            self._wait_for_search()
            stale_generation = page._search_generation
            page.game_name_search_query.setText("Quake")
            client.search_games.return_value = [{"name": "Quake", "id": 2}]
            page._search_games_slot()
            page._on_search_finished(stale_generation, [("Doom", 1)])
            self._wait_for_search()
            self.assertEqual(page.game_list_model.games, [("Quake", 2)])
        finally:
            page.deleteLater()
