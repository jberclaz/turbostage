from unittest import TestCase

from turbostage.igdb_client import IgdbClient


class TestIgdb(TestCase):
    def test_simple_query(self):
        client = IgdbClient()

        result = client.query("games", ["id", "name"], "platforms=13")
        self.assertTrue(len(result) > 0)

    import unittest
    from unittest.mock import MagicMock, patch

    from turbostage.igdb_client import IgdbClient

    class TestIgdbClient(unittest.TestCase):
        def test_simple_search(self):
            with patch("turbostage.igdb_client.IGDBWrapper") as mock_wrapper:
                # Setup mock response
                mock_instance = MagicMock()
                mock_instance.api_request.return_value = b'[{"id": 123, "name": "Test Drive"}]'
                mock_wrapper.return_value = mock_instance

                # Setup mock auth token
                with patch.object(IgdbClient, "_get_auth", return_value="mock_token"):
                    client = IgdbClient()
                    result = client.search("games", ["id", "name", "release_dates"], "Drive", "platforms=(13)")
                    self.assertTrue(len(result) > 0)

                    # Verify correct parameters were used in the API call
                    mock_instance.api_request.assert_called_once()
                    self.assertEqual(mock_instance.api_request.call_args[0][0], "games")
                    self.assertIn('search "Drive"', mock_instance.api_request.call_args[0][1])
                    self.assertIn("platforms=(13)", mock_instance.api_request.call_args[0][1])

    if __name__ == "__main__":
        unittest.main()

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
        self.assertEqual(1, len(result))
        company_ids = set(r["company"] for r in result)
        result = client.query("companies", ["name"], f"id=({','.join(str(i) for i in company_ids)})")
        self.assertEqual(1, len(result))
