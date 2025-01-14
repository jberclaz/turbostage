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
        result = client.query(
            "games",
            [
                "name",
                "summary",
                "storyline",
                "screenshots",
                "rating",
                "release_dates",
                "involved_companies",
                "genres",
                "cover",
            ],
            "id=60",
        )
        self.assertEqual(1, len(result))
        details = result[0]
        result = client.query("covers", ["url"], f"id={details['cover']}")
        self.assertEqual(1, len(result))
        result = client.query(
            "release_dates", ["date"], f"platform=13&id=({','.join([str(d) for d in details['release_dates']])})"
        )
        self.assertEqual(1, len(result))
        result = client.query("genres", ["name"], f"id=({','.join([str(i) for i in details['genres']])})")
        self.assertEqual(3, len(result))
        result = client.query(
            "involved_companies",
            ["company"],
            f"id=({','.join(str(i) for i in details['involved_companies'])})&developer=true",
        )
        self.assertEqual(2, len(result))
        company_ids = set(r["company"] for r in result)
        result = client.query("companies", ["name"], f"id=({','.join(str(i) for i in company_ids)})")
        self.assertEqual(1, len(result))
