from unittest import TestCase

from turbostage.igdb_client import IgdbClient


class TestIgdb(TestCase):
    def test_simple_query(self):
        client = IgdbClient()

        result = client.query("games", ["id", "name"], "platforms=13")
        self.assertTrue(len(result) > 0)

    def test_simple_search(self):
        client = IgdbClient()

        result = client.search("games", ["id", "name", "release_dates"], "Drive", "platforms=(13)")
        self.assertTrue(len(result) > 0)

    def test_platforms(self):
        client = IgdbClient()
        result = client.query("platforms", ["id", "name"])
        self.assertTrue(len(result) > 0)

    def test_game_details(self):
        client = IgdbClient()
        result = client.query("games", ["name", "summary", "storyline", "screenshots", "rating", "release_dates", "involved_companies", "genres", "cover"], "id=60")
        self.assertEqual(1, len(result))
        result = client.query("covers", ["url"], f"id={result[0]['cover']}")
        self.assertEqual(1, len(result))