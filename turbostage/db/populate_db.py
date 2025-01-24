import os
import sqlite3
import zipfile

from PySide6.QtCore import QStandardPaths

from turbostage import utils

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


def initialize_database(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
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
            config TEXT
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
        CREATE TABLE IF NOT EXISTS db_version (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version TEXT NOT NULL
        );
        """
    )

    cursor.execute("""INSERT INTO db_version (version) VALUES (?)""", ("0.0.0",))

    conn.commit()
    conn.close()


def populate_database(db_path, games):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM db_version;")
    cursor.execute("""INSERT INTO db_version (version) VALUES (?)""", ("0.1.0",))

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
            cursor.execute(
                """
                INSERT INTO versions (game_id, version, executable, archive, config)
                VALUES (?, ?, ?, ?, ?)
                """,
                (game_id, version["version"], version["executable"], version["archive"], version["config"]),
            )
            version_id = cursor.lastrowid
            game_archive = os.path.join("games", version["archive"])
            if not os.path.isfile(game_archive):
                print(f"Game {game['title']} not found on disk")
                continue
            hashes = utils.compute_hash_for_largest_files_in_zip(game_archive, n=4)
            if not version["executable"] in [h[0] for h in hashes]:
                with zipfile.ZipFile(game_archive, "r") as zf:
                    h = utils.compute_md5_from_zip(zf, version["executable"])
                    hashes.append((version["executable"], 0, h))
            for h in hashes:
                cursor.execute(
                    """
                    INSERT INTO hashes (version_id, file_name, hash)
                    VALUES (?, ?, ?)""",
                    (version_id, h[0], h[2]),
                )

    conn.commit()
    conn.close()
    print(f"Database populated successfully: {db_path}")


if __name__ == "__main__":
    db_path = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    db_file = os.path.join(db_path, "turbostage.db")
    if os.path.exists(db_file):
        os.remove(db_file)
    initialize_database(db_file)
    populate_database(db_file, GAME_DATA)
