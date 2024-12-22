import os
import sqlite3

GAME_DATA = [
    {
        "title": "The Secret of Monkey Island",
        "release_year": 1990,
        "genre": "Adventure",
        "startup": "monkey/monkey.exe",
        "archive": "monkey.zip",
        "config": "",
    },
    {
        "title": "Prince of Persia",
        "release_year": 1989,
        "genre": "Platformer",
        "startup": "pop/PRINCE.EXE",
        "archive": "pop.zip",
        "config": "",
    },
    {
        "title": "Prince of Persia 2: The Shadow and the Flame",
        "release_year": 1993,
        "genre": "Platformer",
        "startup": "pop2/prince.exe",
        "archive": "pop2.zip",
        "config": "",
    },
    {
        "title": "Comanche: Maximum Overkill",
        "release_year": 1992,
        "genre": "Simulation",
        "startup": "COMANCHE/c.exe",
        "archive": "comanche.zip",
        "config": "[midi]\nmididevice = mt32\n",
    },
    {
        "title": "Power Drive",
        "release_year": 1994,
        "genre": "Racing",
        "startup": "pd/pdrive.exe",
        "archive": "powerdrive.zip",
        "config": "[cpu]\ncpu_cycles = 12000\n",
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
            genre TEXT,
            startup TEXT,
            archive TEXT,
            config TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def populate_database(db_path, games):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for game in games:
        cursor.execute(
            """
            INSERT INTO games (title, release_year, genre, startup, archive, config)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (game["title"], game["release_year"], game["genre"], game["startup"], game["archive"], game["config"]),
        )

    conn.commit()
    conn.close()
    print("Database populated successfully.")


if __name__ == "__main__":
    if os.path.exists("games.db"):
        os.remove("games.db")
    database_path = "games.db"
    initialize_database(database_path)
    populate_database(database_path, GAME_DATA)
