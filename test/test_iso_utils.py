import os
import tempfile
from unittest import TestCase

from turbostage import iso_utils


class TestIsoUtils(TestCase):
    def test_is_iso_file(self):
        """Test the is_iso_file function."""
        self.assertTrue(iso_utils.is_iso_file("/path/to/game.iso"))
        self.assertTrue(iso_utils.is_iso_file("/path/to/game.ISO"))
        self.assertTrue(iso_utils.is_iso_file("/path/to/game.Iso"))
        self.assertFalse(iso_utils.is_iso_file("/path/to/game.zip"))
        self.assertFalse(iso_utils.is_iso_file("/path/to/game.exe"))
        self.assertFalse(iso_utils.is_iso_file("/path/to/game"))

    def test_get_archive_type(self):
        """Test the get_archive_type function."""
        self.assertEqual(iso_utils.get_archive_type("/path/to/game.iso"), "iso")
        self.assertEqual(iso_utils.get_archive_type("/path/to/game.ISO"), "iso")
        self.assertEqual(iso_utils.get_archive_type("/path/to/game.zip"), "zip")
        self.assertEqual(iso_utils.get_archive_type("/path/to/game.ZIP"), "zip")
        self.assertEqual(iso_utils.get_archive_type("/path/to/game.exe"), "zip")


class TestIsoUtilsWithDatabase(TestCase):
    """Tests that require a database connection."""

    def test_add_iso_game_version(self):
        """Test adding a game version with ISO archive type."""
        from turbostage.db.database_manager import DatabaseManager
        from turbostage.db.game_database import GameDatabase

        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "test.db")
            DatabaseManager.initialize_database(db_path)
            db = GameDatabase(db_path)

            # Insert a game
            from turbostage.db.game_database import GameDetails

            game_details = GameDetails(
                title="Test Game",
                release_date=1609459200,
                genre="Action",
                summary="Test summary",
                publisher="Test Publisher",
                developer="Test Developer",
                cover_url="",
                screenshot_urls="[]",
                rating=0,
                igdb_id=12345,
            )
            db.insert_game_with_details("Test Game", game_details)

            # Insert a version
            version_id = db.insert_game_version(12345, "cdrom", "GAME.EXE", None, "", 0)

            # Add local version with ISO type
            db.add_local_game_version(version_id, "test_game.iso", archive_type="iso")

            # Verify archive type
            archive_type = db.get_archive_type(version_id)
            self.assertEqual(archive_type, "iso")

    def test_installation_methods(self):
        """Test installation tracking methods."""
        from turbostage.db.database_manager import DatabaseManager
        from turbostage.db.game_database import GameDatabase

        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "test.db")
            DatabaseManager.initialize_database(db_path)
            db = GameDatabase(db_path)

            # Insert a game and version
            from turbostage.db.game_database import GameDetails

            game_details = GameDetails(
                title="Test Game",
                release_date=1609459200,
                genre="Action",
                summary="Test summary",
                publisher="Test Publisher",
                developer="Test Developer",
                cover_url="",
                screenshot_urls="[]",
                rating=0,
                igdb_id=12345,
            )
            db.insert_game_with_details("Test Game", game_details)
            version_id = db.insert_game_version(12345, "cdrom", "GAME.EXE", None, "", 0)
            db.add_local_game_version(version_id, "test_game.iso", archive_type="iso")

            # Test initial state
            is_installed, install_path = db.get_installation_status(version_id)
            self.assertFalse(is_installed)
            self.assertIsNone(install_path)

            # Create installation
            test_install_path = "/path/to/install"
            db.create_installation(version_id, test_install_path)

            # Test after creation (not yet installed)
            is_installed, install_path = db.get_installation_status(version_id)
            self.assertFalse(is_installed)
            self.assertEqual(install_path, test_install_path)

            # Mark as installed
            db.mark_installed(version_id)

            # Test after marking installed
            is_installed, install_path = db.get_installation_status(version_id)
            self.assertTrue(is_installed)
            self.assertEqual(install_path, test_install_path)

            # Test delete installation
            db.delete_installation(version_id)
            is_installed, install_path = db.get_installation_status(version_id)
            self.assertFalse(is_installed)
            self.assertIsNone(install_path)
