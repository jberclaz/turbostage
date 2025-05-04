import os
import tempfile
import unittest

from turbostage.db.constants import DB_VERSION
from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase, GameDetails


class TestGameDatabase(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for testing
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        # Initialize the database using the DatabaseManager
        DatabaseManager.initialize_database(self.temp_db.name)

        # Define test data constants
        self.test_igdb_id = 12345
        self.test_game_details = GameDetails(
            release_date=946684800,  # 2000-01-01
            genre="Adventure",
            summary="Test game summary",
            publisher="Test Publisher",
            cover_url="//images.igdb.com/test.jpg",
            igdb_id=self.test_igdb_id,
        )

    def tearDown(self):
        # Clean up the temporary database file
        os.unlink(self.temp_db.name)

    def _create_test_game_and_version(self):
        """Helper to create a test game with a version and return their IDs"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details)

        # Insert a version
        version_id = db.insert_game_version(game_id, "1.0", "game.exe", "game.zip", "dosbox_config", 3000)

        # Insert a local version
        db.insert_local_version(version_id, "game.zip")

        return game_id, version_id

    def test_init_database(self):
        """Test database initialization"""
        db = GameDatabase(self.temp_db.name)
        self.assertEqual(db.get_version(), DB_VERSION)

    def test_insert_and_get_game(self):
        """Test inserting a game and retrieving it"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details)
        self.assertIsNotNone(game_id)

        # Retrieve the game
        game = db.get_game_by_igdb_id(self.test_igdb_id)
        self.assertIsNotNone(game)
        self.assertEqual(game[1], "Test Game")  # title
        self.assertEqual(game[4], "Test game summary")  # summary
        self.assertEqual(game[6], self.test_igdb_id)  # igdb_id

    def test_update_game_details(self):
        """Test updating game details"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details)

        # Update the game details
        new_details = GameDetails(
            summary="Updated game summary",
            release_date=978307200,  # 2001-01-01
            genre="Strategy",
            publisher="New Publisher",
            cover_url="//images.igdb.com/new.jpg",
        )

        db.update_game_details(self.test_igdb_id, new_details)

        # Verify the update
        game_details = db.get_game_details_by_igdb_id(self.test_igdb_id)
        self.assertIsNotNone(game_details)
        self.assertEqual(game_details.release_date, new_details.release_date)
        self.assertEqual(game_details.genre, new_details.genre)
        self.assertEqual(game_details.summary, new_details.summary)
        self.assertEqual(game_details.publisher, new_details.publisher)
        self.assertEqual(game_details.cover_url, new_details.cover_url)

    def test_find_game_by_hashes(self):
        """Test finding a game by file hashes"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details)

        # Insert a version
        version_id = db.insert_game_version(game_id, "1.0", "game.exe", "game.zip", "", 0)

        # Insert some hashes
        test_hashes = [("game.exe", 1000, "abc123"), ("data.dat", 5000, "def456"), ("music.mp3", 3000, "ghi789")]

        db.insert_multiple_hashes(version_id, test_hashes)

        # Test finding by one hash
        found_version = db.find_game_by_hashes(["abc123"])
        self.assertEqual(found_version, version_id)

        # Test finding by multiple hashes
        found_version = db.find_game_by_hashes(["def456", "ghi789"])
        self.assertEqual(found_version, version_id)

        # Test finding with non-existent hash
        found_version = db.find_game_by_hashes(["xyz000"])
        self.assertIsNone(found_version)

        # Test finding with empty hash list
        found_version = db.find_game_by_hashes([])
        self.assertIsNone(found_version)

        # Test finding when multiple versions match but with different hash counts
        # Insert a second version with some overlapping hashes
        second_version_id = db.insert_game_version(game_id, "2.0", "game2.exe", "game2.zip", "", 0)

        second_hashes = [("game2.exe", 1000, "abc456"), ("data.dat", 5000, "def456")]  # Same hash as in first version

        db.insert_multiple_hashes(second_version_id, second_hashes)

        # Should find the version with more matches
        found_version = db.find_game_by_hashes(["abc123", "def456", "ghi789"])
        self.assertEqual(found_version, version_id)  # First version has more matches

        # Should find second version if its hashes are more prevalent
        found_version = db.find_game_by_hashes(["def456", "abc456"])
        self.assertEqual(found_version, second_version_id)

    def test_local_versions(self):
        """Test operations related to local versions"""
        game_id, version_id = self._create_test_game_and_version()
        db = GameDatabase(self.temp_db.name)

        # Verify game appears in local versions list
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 1)
        self.assertEqual(games_list[0].igdb_id, self.test_igdb_id)  # igdb_id
        self.assertEqual(games_list[0].title, "Test Game")  # title

        # Clear local versions
        db.clear_local_versions()

        # Verify list is now empty
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 0)

        # Re-add local version
        db.insert_local_version(version_id, "game.zip")

        # Verify it's back
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 1)

    def test_empty_query_results(self):
        """Test behavior with empty query results"""
        db = GameDatabase(self.temp_db.name)

        # Test non-existent game
        game = db.get_game_by_igdb_id(99999)
        self.assertIsNone(game)

        # Test launch info for non-existent version using new method
        launch_info = db.get_version_launch_info(99999)
        self.assertIsNone(launch_info)

        # Test version info for non-existent game using new method
        versions = db.get_version_info(99999)
        self.assertEqual(len(versions), 0)

        # Test empty local versions list
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 0)
