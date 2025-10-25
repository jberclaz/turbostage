import unittest
from unittest.mock import MagicMock, patch

from turbostage.igdb_client import IgdbClient


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
        result = self.client.search_games("Drive")

        # Verify results
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 123)
        self.assertEqual(result[0]["name"], "Test Drive")

        # Verify API call parameters
        self.mock_instance.api_request.assert_called_once()
        self.assertEqual(self.mock_instance.api_request.call_args[0][0], "games")
        self.assertIn('search "Drive"', self.mock_instance.api_request.call_args[0][1])
        self.assertIn("platforms = (13)", self.mock_instance.api_request.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
