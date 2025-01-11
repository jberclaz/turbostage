from unittest import TestCase

from turbostage.igdb import Igdb


class TestIgdb(TestCase):
    def test_simple_query(self):
        client = Igdb()

        result = client.query("games", ["id", "name"], "platforms=13")
        self.assertTrue(len(result) > 0)

    def test_simple_search(self):
        client = Igdb()

        result = client.search("games", ["id", "name", "platforms"], "Indiana", "platforms=(13)")
        self.assertTrue(len(result) > 0)

    def test_platforms(self):
        client = Igdb()
        result = client.query("platforms", ["id", "name"])
        self.assertTrue(len(result) > 0)