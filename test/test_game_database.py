import os
import tempfile
import unittest

from turbostage.db.constants import DB_VERSION
from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase


class TestGameDatabase(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for testing
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        # Initialize the database using the DatabaseManager
        DatabaseManager.initialize_database(self.temp_db.name)

        # Define test data constants
        self.test_igdb_id = 12345
        self.test_game_details = {
            "summary": "Test game summary",
            "release_date": 946684800,  # 2000-01-01
            "genres": "Adventure",
            "publisher": "Test Publisher",
            "cover": "//images.igdb.com/test.jpg",
        }

    def tearDown(self):
        # Clean up the temporary database file
        os.unlink(self.temp_db.name)

    def _create_test_game_and_version(self):
        """Helper to create a test game with a version and return their IDs"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details, self.test_igdb_id)

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
        game_id = db.insert_game_with_details("Test Game", self.test_game_details, self.test_igdb_id)
        self.assertIsNotNone(game_id)

        # Retrieve the game
        game = db.get_game_by_igdb_id(self.test_igdb_id)
        self.assertIsNotNone(game)
        self.assertEqual(game[1], "Test Game")  # title
        self.assertEqual(game[2], "Test game summary")  # summary
        self.assertEqual(game[6], self.test_igdb_id)  # igdb_id

    def test_update_game_details(self):
        """Test updating game details"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details, self.test_igdb_id)

        # Update the game details
        new_summary = "Updated game summary"
        new_release_date = 978307200  # 2001-01-01
        new_genre = "Strategy"
        new_publisher = "New Publisher"
        new_cover_url = "//images.igdb.com/new.jpg"

        db.update_game_details(
            self.test_igdb_id, new_summary, new_release_date, new_genre, new_publisher, new_cover_url
        )

        # Verify the update
        game_details = db.get_game_details_by_igdb_id(self.test_igdb_id)
        self.assertIsNotNone(game_details)
        self.assertEqual(game_details[0], new_release_date)  # release_date
        self.assertEqual(game_details[1], new_genre)  # genre
        self.assertEqual(game_details[2], new_summary)  # summary
        self.assertEqual(game_details[3], new_publisher)  # publisher
        self.assertEqual(game_details[4], new_cover_url)  # cover_url

    def test_find_game_by_hashes(self):
        """Test finding a game by file hashes"""
        db = GameDatabase(self.temp_db.name)

        # Insert a test game
        game_id = db.insert_game_with_details("Test Game", self.test_game_details, self.test_igdb_id)

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

    def test_game_launch_info(self):
        """Test retrieving game launch information"""
        game_id, version_id = self._create_test_game_and_version()
        db = GameDatabase(self.temp_db.name)

        # Test getting launch info
        launch_info = db.get_game_launch_info(self.test_igdb_id)
        self.assertIsNotNone(launch_info)
        self.assertEqual(launch_info[0], "game.exe")  # executable
        self.assertEqual(launch_info[1], "game.zip")  # archive
        self.assertEqual(launch_info[2], "dosbox_config")  # config
        self.assertEqual(launch_info[3], 3000)  # cycles
        self.assertEqual(launch_info[4], version_id)  # version_id

    def test_config_files_operations(self):
        """Test config file operations"""
        _, version_id = self._create_test_game_and_version()
        db = GameDatabase(self.temp_db.name)

        # Add config files
        config_type = 1  # CONFIG
        config_files = {
            "conf/dosbox.conf": b"[sdl]\nfullscreen=true\n",
            "conf/mapper.txt": b"mapping data here",
            "saves/save.dat": b"save game data",
        }

        db.add_extra_files(config_files, version_id, config_type)

        # Get config files
        retrieved_files = db.get_config_files_with_content(version_id, config_type)
        self.assertEqual(len(retrieved_files), 3)

        # Verify content
        file_dict = {path: content for path, content in retrieved_files}
        self.assertEqual(file_dict["conf/dosbox.conf"], b"[sdl]\nfullscreen=true\n")
        self.assertEqual(file_dict["conf/mapper.txt"], b"mapping data here")
        self.assertEqual(file_dict["saves/save.dat"], b"save game data")

        # Get metadata
        metadata = db.get_config_files_metadata(version_id, config_type)
        self.assertEqual(len(metadata), 3)

        # Update a file
        updated_files = {"conf/dosbox.conf": b"[sdl]\nfullscreen=false\n"}
        db.add_extra_files(updated_files, version_id, config_type)

        # Verify update
        retrieved_files = db.get_config_files_with_content(version_id, config_type)
        file_dict = {path: content for path, content in retrieved_files}
        self.assertEqual(file_dict["conf/dosbox.conf"], b"[sdl]\nfullscreen=false\n")

        # Test different file type
        save_type = 2  # SAVEGAME
        save_files = {"saves/save1.sav": b"save game data 1", "saves/save2.sav": b"save game data 2"}

        db.add_extra_files(save_files, version_id, save_type)

        # Verify config files and save files are separate
        config_files = db.get_config_files_with_content(version_id, config_type)
        save_files = db.get_config_files_with_content(version_id, save_type)

        self.assertEqual(len(config_files), 3)
        self.assertEqual(len(save_files), 2)

    def test_delete_game(self):
        """Test deleting a game and all its dependencies"""
        self._create_test_game_and_version()
        db = GameDatabase(self.temp_db.name)

        # Add some config files
        config_type = 1  # CONFIG
        config_files = {"conf/dosbox.conf": b"[sdl]\nfullscreen=true\n"}

        # Get version ID for the game
        launch_info = db.get_game_launch_info(self.test_igdb_id)
        version_id = launch_info[4]

        db.add_extra_files(config_files, version_id, config_type)

        # Verify game exists
        game = db.get_game_by_igdb_id(self.test_igdb_id)
        self.assertIsNotNone(game)

        # Delete the game
        db.delete_game_by_igdb_id(self.test_igdb_id)

        # Verify game is gone
        game = db.get_game_by_igdb_id(self.test_igdb_id)
        self.assertIsNone(game)

        # Verify version is gone (by checking config files)
        config_files = db.get_config_files_with_content(version_id, config_type)
        self.assertEqual(len(config_files), 0)

    def test_local_versions(self):
        """Test operations related to local versions"""
        game_id, version_id = self._create_test_game_and_version()
        db = GameDatabase(self.temp_db.name)

        # Verify game appears in local versions list
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 1)
        self.assertEqual(games_list[0][0], self.test_igdb_id)  # igdb_id
        self.assertEqual(games_list[0][1], "Test Game")  # title

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

    def test_find_setup_executables(self):
        """Test finding setup executables"""
        game_id, version_id = self._create_test_game_and_version()
        db = GameDatabase(self.temp_db.name)

        # Add some hashes with setup executables
        setup_hashes = [
            ("setup.exe", 1000, "setup123"),
            ("install.exe", 2000, "install456"),  # Not matched by current implementation
            ("SETUP2.EXE", 3000, "setup789"),  # This will match because of lower() in the SQL
            ("not_setup.exe", 4000, "other123"),  # This will match due to 'setup' in name
        ]

        db.insert_multiple_hashes(version_id, setup_hashes)

        # Find setup executables - files with 'setup' in lowercase name are found
        setup_exes = db.find_setup_executables(version_id)

        # Let's print for debugging
        print(f"Found setup executables: {setup_exes}")

        # Should include setup.exe, SETUP2.EXE (due to lower() in SQL), and not_setup.exe
        self.assertEqual(len(setup_exes), 3)
        self.assertIn("setup.exe", setup_exes)
        self.assertIn("SETUP2.EXE", setup_exes)
        self.assertIn("not_setup.exe", setup_exes)
        self.assertNotIn("install.exe", setup_exes)

    def test_empty_query_results(self):
        """Test behavior with empty query results"""
        db = GameDatabase(self.temp_db.name)

        # Test non-existent game
        game = db.get_game_by_igdb_id(99999)
        self.assertIsNone(game)

        # Test launch info for non-existent game
        launch_info = db.get_game_launch_info(99999)
        self.assertIsNone(launch_info)

        # Test version info for non-existent game
        version_info = db.get_version_info_by_game_id(99999)
        self.assertIsNone(version_info)

        # Test empty local versions list
        games_list = db.get_games_with_local_versions()
        self.assertEqual(len(games_list), 0)
