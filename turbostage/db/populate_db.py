import importlib.resources
import json
import os
import sqlite3
import zipfile

from PySide6.QtCore import QStandardPaths

from turbostage import utils
from turbostage.db.constants import DB_VERSION
from turbostage.db.database_manager import DatabaseManager


def load_sample_game_data():
    """Load sample game data from JSON file.

    Returns:
        List of game dictionaries with title, versions, and igdb_id
    """
    try:
        # Use importlib.resources for a more robust way to access package resources
        sample_games_path = importlib.resources.files("turbostage.content").joinpath("sample_games.json")
        with open(sample_games_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading sample game data: {e}")
        return []


def populate_database(db_path, games):
    """Populate the database with sample game data.

    Args:
        db_path: Path to the SQLite database file
        games: List of game dictionaries with title, versions, and igdb_id
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure the database version is correct
    cursor.execute("DELETE FROM db_version")
    cursor.execute("INSERT INTO db_version (version) VALUES (?)", (DB_VERSION,))

    # Add game data
    for game in games:
        cursor.execute(
            """
            INSERT INTO games (title, igdb_id)
            VALUES (?, ?)
            """,
            (game["title"], game["igdb_id"]),
        )
        game_id = cursor.lastrowid

        for version in game["versions"]:
            # Convert cycles if present, otherwise use default value 0
            cycles = version.get("cycles", 0)

            cursor.execute(
                """
                INSERT INTO versions (game_id, version, executable, archive, config, cycles)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (game_id, version["version"], version["executable"], version["archive"], version["config"], cycles),
            )
            version_id = cursor.lastrowid

            # Process game files and create hashes
            game_archive = os.path.join("games", version["archive"])
            if not os.path.isfile(game_archive):
                print(f"Game {game['title']} not found on disk")
                continue

            hashes = utils.compute_hash_for_largest_files_in_zip(game_archive, n=4)

            # Ensure the executable is included in hashes
            if not version["executable"] in [h[0] for h in hashes]:
                with zipfile.ZipFile(game_archive, "r") as zf:
                    h = utils.compute_md5_from_zip(zf, version["executable"])
                    hashes.append((version["executable"], 0, h))

            # Add hashes to database
            for h in hashes:
                cursor.execute(
                    """
                    INSERT INTO hashes (version_id, file_name, hash)
                    VALUES (?, ?, ?)
                    """,
                    (version_id, h[0], h[2]),
                )

    conn.commit()
    conn.close()
    print(f"Database populated successfully: {db_path}")


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
