import sqlite3
from unittest import TestCase
from unittest.mock import patch

import requests

from turbostage.db.migrations import migrate_to_0_9_0


def _pre_0_9_0_db(igdb_ids):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (igdb_id INTEGER, title TEXT)")
    conn.executemany("INSERT INTO games (igdb_id, title) VALUES (?, ?)", [(i, f"Game {i}") for i in igdb_ids])
    return conn


def _info(developer):
    return {"developer": developer, "screenshot_urls": ["https://x/1.jpg"], "rating": 80}


class TestMigrateTo090(TestCase):
    def _rows(self, conn):
        return conn.execute("SELECT igdb_id, developer, screenshot_urls, rating FROM games ORDER BY igdb_id").fetchall()

    def test_backfills_every_game(self):
        conn = _pre_0_9_0_db([1, 2])
        with patch("turbostage.db.migrations.IgdbClient") as client_cls:
            client_cls.return_value.get_game_info.side_effect = lambda igdb_id: _info(f"Dev {igdb_id}")
            migrate_to_0_9_0(conn)
        self.assertEqual(
            self._rows(conn),
            [(1, "Dev 1", '["https://x/1.jpg"]', 80), (2, "Dev 2", '["https://x/1.jpg"]', 80)],
        )

    def test_offline_adds_columns_and_stops_at_first_failure(self):
        conn = _pre_0_9_0_db([1, 2, 3])
        with patch("turbostage.db.migrations.IgdbClient") as client_cls:
            client_cls.return_value.get_game_info.side_effect = requests.exceptions.ConnectionError("offline")
            migrate_to_0_9_0(conn)
            client_cls.return_value.get_game_info.assert_called_once()
        self.assertEqual(self._rows(conn), [(1, None, "[]", 0), (2, None, "[]", 0), (3, None, "[]", 0)])

    def test_unknown_game_is_skipped(self):
        conn = _pre_0_9_0_db([1, 2])
        with patch("turbostage.db.migrations.IgdbClient") as client_cls:
            client_cls.return_value.get_game_info.side_effect = [None, _info("Dev 2")]
            migrate_to_0_9_0(conn)
        self.assertEqual(self._rows(conn), [(1, None, "[]", 0), (2, "Dev 2", '["https://x/1.jpg"]', 80)])

    def test_empty_library(self):
        conn = _pre_0_9_0_db([])
        with patch("turbostage.db.migrations.IgdbClient") as client_cls:
            migrate_to_0_9_0(conn)
            client_cls.return_value.get_game_info.assert_not_called()
        self.assertEqual(self._rows(conn), [])
