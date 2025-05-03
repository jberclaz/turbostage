import unittest
from unittest.mock import MagicMock, patch

from turbostage.igdb_client import IgdbClient


class TestIgdb(unittest.TestCase):
    """Tests for basic IGDB client functionality using mocks."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create mock for the IGDB wrapper
        self.wrapper_patch = patch("turbostage.igdb_client.IGDBWrapper")
        self.mock_wrapper = self.wrapper_patch.start()

        # Setup mock response
        self.mock_instance = MagicMock()
        self.mock_wrapper.return_value = self.mock_instance

        # Setup mock auth token
        self.auth_patch = patch.object(IgdbClient, "_get_auth", return_value="mock_token")
        self.auth_patch.start()

        # Create client instance
        self.client = IgdbClient()

    def tearDown(self):
        """Clean up after each test."""
        self.wrapper_patch.stop()
        self.auth_patch.stop()

    def test_simple_query(self):
        """Test a simple query to the IGDB API."""
        import json

        # Setup mock response
        mock_data = [{"id": 1, "name": "Test Game 1"}, {"id": 2, "name": "Test Game 2"}]
        self.mock_instance.api_request.return_value = json.dumps(mock_data).encode("utf-8")

        # Execute query
        result = self.client.query("games", ["id", "name"], "platforms=13")

        # Verify results
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Test Game 1")
        self.assertEqual(result[1]["name"], "Test Game 2")

        # Verify API call
        self.mock_instance.api_request.assert_called_once()
        self.assertEqual(self.mock_instance.api_request.call_args[0][0], "games")
        self.assertIn("platforms=13", self.mock_instance.api_request.call_args[0][1])

    def test_platforms(self):
        """Test retrieving platform information."""
        import json

        # Setup mock response
        mock_data = [{"id": 13, "name": "PC"}, {"id": 6, "name": "DOS"}]
        self.mock_instance.api_request.return_value = json.dumps(mock_data).encode("utf-8")

        # Execute query
        result = self.client.query("platforms", ["id", "name"])

        # Verify results
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "PC")
        self.assertEqual(result[1]["name"], "DOS")

        # Verify API call
        self.mock_instance.api_request.assert_called_once()
        self.assertEqual(self.mock_instance.api_request.call_args[0][0], "platforms")

    def test_game_details(self):
        """Test retrieving detailed game information."""
        import json

        # Setup mock responses for multiple calls
        game_response = [
            {
                "name": "The Witcher 3",
                "summary": "A great RPG",
                "storyline": "Geralt's adventures",
                "screenshots": [1, 2],
                "rating": 95,
                "release_dates": [101, 102],
                "involved_companies": [201, 202],
                "genres": [301, 302, 303],
                "cover": 401,
            }
        ]

        cover_response = [{"url": "//images.igdb.com/cover.jpg"}]
        release_dates_response = [{"date": 1431388800}]  # 2015-05-12
        genres_response = [{"name": "RPG"}, {"name": "Adventure"}, {"name": "Open World"}]
        companies_response = [{"name": "CD Projekt RED"}]
        involved_companies_response = [{"company": 501}, {"company": 502}]

        # Setup sequential mock responses using proper JSON serialization
        self.mock_instance.api_request.side_effect = [
            json.dumps(game_response).encode("utf-8"),
            json.dumps(cover_response).encode("utf-8"),
            json.dumps(release_dates_response).encode("utf-8"),
            json.dumps(genres_response).encode("utf-8"),
            json.dumps(involved_companies_response).encode("utf-8"),
            json.dumps(companies_response).encode("utf-8"),
        ]

        # Execute queries
        result = self.client.query(
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

        result = self.client.query("covers", ["url"], f"id={details['cover']}")
        self.assertEqual(1, len(result))

        result = self.client.query(
            "release_dates", ["date"], f"platform=13&id=({','.join([str(d) for d in details['release_dates']])})"
        )
        self.assertEqual(1, len(result))

        result = self.client.query("genres", ["name"], f"id=({','.join([str(i) for i in details['genres']])})")
        self.assertEqual(3, len(result))

        result = self.client.query(
            "involved_companies",
            ["company"],
            f"id=({','.join(str(i) for i in details['involved_companies'])})&developer=true",
        )
        self.assertEqual(len(result), 2)

        company_ids = set(r["company"] for r in result)
        result = self.client.query("companies", ["name"], f"id=({','.join(str(i) for i in company_ids)})")
        self.assertEqual(1, len(result))

        # Verify number of API calls
        self.assertEqual(self.mock_instance.api_request.call_count, 6)


class TestIgdbSearch(unittest.TestCase):
    """Tests for the search functionality of the IGDB client."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create mock for the IGDB wrapper
        self.wrapper_patch = patch("turbostage.igdb_client.IGDBWrapper")
        self.mock_wrapper = self.wrapper_patch.start()

        # Setup mock response
        self.mock_instance = MagicMock()
        self.mock_wrapper.return_value = self.mock_instance

        # Setup mock auth token
        self.auth_patch = patch.object(IgdbClient, "_get_auth", return_value="mock_token")
        self.auth_patch.start()

        # Create client instance
        self.client = IgdbClient()

    def tearDown(self):
        """Clean up after each test."""
        self.wrapper_patch.stop()
        self.auth_patch.stop()

    def test_simple_search(self):
        """Test searching for games by name."""
        # Setup mock response
        self.mock_instance.api_request.return_value = b'[{"id": 123, "name": "Test Drive"}]'

        # Execute search
        result = self.client.search("games", ["id", "name", "release_dates"], "Drive", "platforms=(13)")

        # Verify results
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 123)
        self.assertEqual(result[0]["name"], "Test Drive")

        # Verify API call parameters
        self.mock_instance.api_request.assert_called_once()
        self.assertEqual(self.mock_instance.api_request.call_args[0][0], "games")
        self.assertIn('search "Drive"', self.mock_instance.api_request.call_args[0][1])
        self.assertIn("platforms=(13)", self.mock_instance.api_request.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
