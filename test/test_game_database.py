import os
import tempfile
import unittest
from unittest.mock import MagicMock

from turbostage.db.constants import DB_VERSION
from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase, GameDetails
from turbostage.igdb_client import IgdbClient

SUBMISSION_DATA = {
    "generated_at": "2025-11-01T14:24:29.992062",
    "games": {
        7494: {
            "versions": {
                "default": {
                    "executable": "COMANCHE/COMANCHE.EXE",
                    "config_executable": "COMANCHE/SOUNDSET.EXE",
                    "config": None,
                    "cycles": 0,
                    "hashes": {
                        "C2.DTA": "3e1c2630f375acc3c72e46b240acbc28",
                        "C3.DTA": "f5a63082dc80b282b9bbd74bd0112aa7",
                        "C4.DTA": "27a8eb41f6ebe1aa953b45aa7d0486c4",
                        "D3.DTA": "d8326fde92627036f6066a02eabd7f32",
                        "COMANCHE.EXE": "a5f3ec228ce9c9c6e6e455281bde75ef",
                    },
                }
            }
        },
        273066: {
            "versions": {
                "default": {
                    "executable": "Arkanoid_2_-_Revenge_of_Doh/DOH.EXE",
                    "config_executable": None,
                    "config": None,
                    "cycles": 0,
                    "hashes": {
                        "REVOFDOH.EGA": "4726a22b0b3f73a48f57e3f1796ae10b",
                        "REVOFDOH.DAT": "f66b0b2f8b3f888d254b5ecf3317ec78",
                        "REVOFDOH.CGA": "e3e0c075ca8593517afa222b9757541e",
                        "REVOFDOH.TGA": "20079499b7f54471cbdaa3eda9a07f21",
                        "DOH.EXE": "ab2cd958cbe3aa314d1f3264f8d439e3",
                    },
                }
            }
        },
    },
}


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
            title="Test Game",
            release_date=946684800,  # 2000-01-01
            genre="Adventure",
            summary="Test game summary",
            publisher="Test Publisher",
            cover_url="//images.igdb.com/test.jpg",
            igdb_id=self.test_igdb_id,
            developer="Test Developer",
            rating=78,
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
        version_id = db.insert_game_version(game_id, "1.0", "game.exe", "setup.exe", "dosbox_config", 3000)

        # Insert a local version
        db.add_local_game_version(version_id, "game.zip")

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
        game = db.get_game_details_by_igdb_id(self.test_igdb_id)
        self.assertIsNotNone(game)
        self.assertEqual(game.title, "Test Game")  # title
        self.assertEqual(game.summary, "Test game summary")  # summary

    def test_update_game_details(self):
        """Test updating game details"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details)

        # Update the game details
        new_details = GameDetails(
            title="Test Game",
            summary="Updated game summary",
            release_date=978307200,  # 2001-01-01
            genre="Strategy",
            publisher="New Publisher",
            cover_url="//images.igdb.com/new.jpg",
            developer="New Developer",
            rating=56,
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
        version_id = db.insert_game_version(game_id, "1.0", "game.exe", "setup.exe", "", 0)

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
        second_version_id = db.insert_game_version(game_id, "2.0", "game2.exe", "setup.exe", "", 0)

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
        db.add_local_game_version(version_id, "game.zip")

        # Verify it's back
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 1)

    def test_empty_query_results(self):
        """Test behavior with empty query results"""
        db = GameDatabase(self.temp_db.name)

        # Test non-existent game
        game = db.get_game_details_by_igdb_id(99999)
        self.assertIsNone(game)

        # Test launch info for non-existent version using new method
        launch_info = db.get_version_by_version_id(99999)
        self.assertIsNone(launch_info)

        # Test version info for non-existent game using new method
        versions = db.get_all_game_versions(99999)
        self.assertEqual(len(versions), 0)

        # Test empty local versions list
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 0)

    def test_merge_remote(self):
        igdb_client = MagicMock()
        igdb_client.get_game_info.side_effect = [
            {
                "name": "name",
                "release_date": 2,
                "genres": ["action"],
                "summary": "resume",
                "publisher": "me",
                "developer": "my brother",
                "cover_url": "http://image.png",
                "rating": 3,
                "screenshot_urls": "",
            },
            {
                "name": "name2",
                "release_date": 3,
                "genres": ["action"],
                "summary": "resume2",
                "publisher": "me",
                "developer": "my brother",
                "cover_url": "http://image.png",
                "rating": 3,
                "screenshot_urls": "",
            },
        ]
        db = GameDatabase(self.temp_db.name)
        db.merge_remote_json(SUBMISSION_DATA, igdb_client)

    def test_resolve_local_executables_by_hash(self):
        """Test that executables can be resolved by matching hashes, even when
        local file paths differ from the stored canonical paths."""
        db = GameDatabase(self.temp_db.name)

        game_id = db.insert_game_with_details("Test Game", self.test_game_details)
        version_id = db.insert_game_version(game_id, "1.0", "GAME.EXE", "SETUP.EXE", "", 0)

        # Add the version to local_versions so get_version_by_version_id finds it
        db.add_local_game_version(version_id, "test_archive.zip")

        # Store hashes for the known version's files (canonical paths)
        db.insert_multiple_hashes(version_id, [
            ("GAME.EXE", 1000, "hash_game"),
            ("SETUP.EXE", 500, "hash_setup"),
            ("DATA.DAT", 5000, "hash_data"),
        ])

        # Simulate local hashes from a user's archive — same content (same hash)
        # but the game executable is at a different relative path
        local_hashes = [
            ("GAMES/GAME.EXE", 1000, "hash_game"),
            ("SETUP.EXE", 500, "hash_setup"),
            ("DATA.DAT", 5000, "hash_data"),
        ]

        # Replicate the _find_local_executables logic:
        version_hashes = db.get_version_hashes(version_id)
        version_hash_map = {fn: h for fn, h in version_hashes}
        local_hash_map = {h: fn for fn, _, h in local_hashes}

        version_info = db.get_version_by_version_id(version_id)

        # Resolve executable
        expected_hash = version_hash_map.get(version_info.executable)
        local_executable = local_hash_map.get(expected_hash) if expected_hash else None

        # Resolve config executable
        expected_config_hash = version_hash_map.get(version_info.config_executable)
        local_config_executable = local_hash_map.get(expected_config_hash) if expected_config_hash else None

        self.assertEqual(local_executable, "GAMES/GAME.EXE")
        self.assertEqual(local_config_executable, "SETUP.EXE")

    def test_resolve_local_executables_via_db_method(self):
        """Test the GameDatabase.resolve_local_executables method directly."""
        db = GameDatabase(self.temp_db.name)

        game_id = db.insert_game_with_details("Test Game", self.test_game_details)
        version_id = db.insert_game_version(game_id, "1.0", "GAME.EXE", "SETUP.EXE", "", 0)
        db.add_local_game_version(version_id, "test_archive.zip")
        db.insert_multiple_hashes(version_id, [
            ("GAME.EXE", 1000, "hash_game"),
            ("SETUP.EXE", 500, "hash_setup"),
            ("DATA.DAT", 5000, "hash_data"),
        ])

        local_hashes = [
            ("GAMES/GAME.EXE", 1000, "hash_game"),
            ("SETUP.EXE", 500, "hash_setup"),
            ("DATA.DAT", 5000, "hash_data"),
        ]

        exec_path, config_exec_path = db.resolve_local_executables(version_id, local_hashes)
        self.assertEqual(exec_path, "GAMES/GAME.EXE")
        self.assertEqual(config_exec_path, "SETUP.EXE")
