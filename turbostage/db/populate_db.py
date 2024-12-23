import os
import sqlite3
import zipfile

from turbostage import utils
from turbostage.main_window import MainWindow

GAME_DATA = [
    {
        "title": "The Secret of Monkey Island",
        "release_year": 1990,
        "genre": "Adventure",
        "versions": [
            {
                "version": "vga",
                "executable": "monkey/MONKEY.EXE",
                "archive": "monkey_vga.zip",
                "config": "",
            }
        ],
    },
    {
        "title": "Prince of Persia",
        "release_year": 1989,
        "genre": "Platformer",
        "versions": [
            {
                "version": "v1.4",
                "executable": "pop/PRINCE.EXE",
                "archive": "pop-1.4.zip",
                "config": "",
            }
        ],
    },
    {
        "title": "Prince of Persia 2: The Shadow and the Flame",
        "release_year": 1993,
        "genre": "Platformer",
        "versions": [
            {
                "version": "en",
                "executable": "pop2/prince.exe",
                "archive": "pop2-en.zip",
                "config": "",
            }
        ],
    },
    {
        "title": "Comanche: Maximum Overkill",
        "release_year": 1992,
        "genre": "Simulation",
        "versions": [
            {
                "version": "en",
                "executable": "COMANCHE/C.EXE",
                "archive": "comanche.zip",
                "config": "[midi]\nmididevice = mt32\n",
            }
        ],
    },
    {
        "title": "Power Drive",
        "release_year": 1994,
        "genre": "Racing",
        "versions": [
            {
                "version": "en",
                "executable": "pd/PDRIVE.EXE",
                "archive": "powerdrive.zip",
                "config": "[cpu]\ncpu_cycles = 12000\n",
            }
        ],
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
            release_year INTEGER,
            genre TEXT
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
        )"""
    )
    conn.commit()
    conn.close()


def populate_database(db_path, games):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for game in games:
        cursor.execute(
            """
            INSERT INTO games (title, release_year, genre)
            VALUES (?, ?, ?)
        """,
            (game["title"], game["release_year"], game["genre"]),
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
            game_archive = os.path.join(MainWindow.GAMES_PATH, version["archive"])
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
    print("Database populated successfully.")


if __name__ == "__main__":
    db_file = MainWindow.DB_PATH
    if os.path.exists(db_file):
        os.remove(db_file)
    initialize_database(db_file)
    populate_database(db_file, GAME_DATA)
