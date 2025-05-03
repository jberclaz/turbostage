import os
import sqlite3
import zipfile

from PySide6.QtCore import QStandardPaths

from turbostage import utils

# Current database version - used for new installations and migrations
DB_VERSION = "0.6.0"

# Original schema version - for reference
ORIGINAL_VERSION = "0.5.0"

GAME_DATA = [
    {
        "title": "The Secret of Monkey Island",
        "versions": [
            {
                "version": "vga",
                "executable": "monkey/MONKEY.EXE",
                "archive": "monkey_vga.zip",
                "config": "",
            }
        ],
        "igdb_id": 60,
    },
    {
        "title": "Prince of Persia",
        "versions": [
            {
                "version": "v1.4",
                "executable": "pop/PRINCE.EXE",
                "archive": "pop-1.4.zip",
                "config": "",
            }
        ],
        "igdb_id": 284766,
    },
    {
        "title": "Prince of Persia 2: The Shadow and the Flame",
        "versions": [
            {
                "version": "en",
                "executable": "pop2/prince.exe",
                "archive": "pop2-en.zip",
                "config": "",
            }
        ],
        "igdb_id": 3164,
    },
    {
        "title": "Comanche: Maximum Overkill",
        "versions": [
            {
                "version": "en",
                "executable": "COMANCHE/C.EXE",
                "archive": "comanche.zip",
                "config": "[midi]\nmididevice = mt32\n",
            }
        ],
        "igdb_id": 7494,
    },
    {
        "title": "Power Drive",
        "versions": [
            {
                "version": "en",
                "executable": "pd/PDRIVE.EXE",
                "archive": "powerdrive.zip",
                "config": "[cpu]\ncpu_cycles = 12000\n",
            }
        ],
        "igdb_id": 12720,
    },
]


def create_schema(conn: sqlite3.Connection):
    """Create the initial database schema.

    This function creates the base schema for a new installation.

    Args:
        conn: An open SQLite connection
    """
    cursor = conn.cursor()

    # Create tables
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            release_date INTEGER,
            genre TEXT,
            summary TEXT,
            publisher TEXT,
            igdb_id INTEGER,
            cover_url TEXT
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            version TEXT,
            executable TEXT,
            archive TEXT,
            config TEXT,
            cycles INTEGER DEFAULT 0
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            file_name TEXT,
            hash TEXT
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS local_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            archive TEXT
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            path TEXT,
            content BLOB,
            name TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS db_version (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version TEXT NOT NULL
        );
        """
    )

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_igdb_id ON games(igdb_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_game_id ON versions(game_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hashes_version_id ON hashes(version_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hashes_hash ON hashes(hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_files_version_id ON config_files(version_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_files_version_path ON config_files(version_id, path, type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_local_versions_version_id ON local_versions(version_id)")

    # Set the database version
    cursor.execute("INSERT INTO db_version (version) VALUES (?)", (DB_VERSION,))


def initialize_database(db_path: str):
    """Initialize a new database or upgrade an existing one.

    This function checks if the database exists. If not, it creates a new one with the latest schema.
    If it exists, it checks the version and applies any necessary migrations.

    Args:
        db_path: Path to the SQLite database file
    """
    db_exists = os.path.exists(db_path)

    conn = sqlite3.connect(db_path)

    if not db_exists:
        # New database, create the schema
        create_schema(conn)
        conn.commit()
        conn.close()
        return

    # Existing database, check version and migrate if needed
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT version FROM db_version ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        current_version = row[0] if row else ORIGINAL_VERSION

        if current_version != DB_VERSION:
            # Import migrations module here to avoid circular imports
            from turbostage.db.migrations import migrate_database

            migrate_database(conn, current_version, DB_VERSION)

            # Ensure the version is updated
            cursor.execute("DELETE FROM db_version")
            cursor.execute("INSERT INTO db_version (version) VALUES (?)", (DB_VERSION,))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error during version check or migration: {e}")
        raise
    finally:
        conn.close()


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

    initialize_database(db_file)
    populate_database(db_file, GAME_DATA)
