"""Development-only sample database seeder.

Rebuilds a throwaway database from turbostage/content/sample_games.json
using the GameDatabase API (so it tracks the current schema).
"""

import importlib.resources
import json
import logging
import os

from PySide6.QtCore import QStandardPaths

from turbostage import utils
from turbostage.db.constants import DB_VERSION
from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase, GameDetails

logger = logging.getLogger(__name__)


def load_sample_game_data():
    """Load sample game data from JSON file.

    Returns:
        List of game dictionaries with title, versions, and igdb_id
    """
    try:
        sample_games_path = importlib.resources.files("turbostage.content").joinpath("sample_games.json")
        with open(sample_games_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading sample game data: {e}")
        return []


def populate_database(db_path, games):
    """Populate the database with sample game data via the GameDatabase API.

    Args:
        db_path: Path to the SQLite database file
        games: List of game dictionaries with title, versions, and igdb_id
    """
    db = GameDatabase(db_path)
    try:
        for game in games:
            title, igdb_id = game["title"], game["igdb_id"]
            if db.get_game_details_by_igdb_id(igdb_id) is None:
                db.insert_game_with_details(
                    title,
                    GameDetails(
                        title=title,
                        release_date=None,
                        genre="",
                        summary="",
                        publisher="",
                        developer="",
                        cover_url="",
                        rating=None,
                        igdb_id=igdb_id,
                        screenshot_urls="[]",
                    ),
                )
            for version in game["versions"]:
                version_id = db.insert_game_version(
                    igdb_id,
                    version["version"],
                    version.get("executable"),
                    None,
                    version.get("config", ""),
                    version.get("cycles", 0),
                )
                game_archive = os.path.join("games", version["archive"])
                if not os.path.isfile(game_archive):
                    print(f"Game {title} not found on disk")
                    continue
                _archive_type, hashes = utils.hash_for_new_version(game_archive, version.get("executable"))
                db.insert_multiple_hashes(version_id, hashes)
                db.add_local_game_version(version_id, version["archive"])
    finally:
        db.close()
    print(f"Database populated successfully: {db_path} (schema {DB_VERSION})")


if __name__ == "__main__":
    db_path = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    db_file = os.path.join(db_path, "turbostage.db")

    # For development purposes, remove existing database before recreating
    if os.path.exists(db_file):
        os.remove(db_file)

    # Initialize the database using the centralized manager
    DatabaseManager.initialize_database(db_file)

    # Load game data from the JSON file
    game_data = load_sample_game_data()
    if game_data:
        populate_database(db_file, game_data)
    else:
        print("Warning: No game data loaded, database will be empty")
