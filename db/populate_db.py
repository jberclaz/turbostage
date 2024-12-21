import os
import sqlite3

GAME_DATA = [
    {"title": "The Secret of Monkey Island", "release_year": 1990, "genre": "Adventure", "config": "", "archive": ""},
    {"title": "Need for Speed", "release_year": 1994, "genre": "Racing", "config": "", "archive": ""},
    {"title": "DOOM", "release_year": 1993, "genre": "Shooter", "config": "", "archive": ""},
    {"title": "SimCity 2000", "release_year": 1993, "genre": "Simulation", "config": "", "archive": ""},
    {
        "title": "Prince of Persia",
        "release_year": 1989,
        "genre": "Platformer",
        "config": "pop/PRINCE.EXE",
        "archive": "pop.zip",
    },
    {
        "title": "Prince of Persia 2: The Shadow and the Flame",
        "release_year": 1993,
        "genre": "Platformer",
        "config": "pop2/prince.exe",
        "archive": "pop2.zip",
    },
    {
        "title": "Comanche: Maximum Overkill",
        "release_year": 1992,
        "genre": "Simulation",
        "config": "COMANCHE/c.exe",
        "archive": "comanche.zip",
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
            config TEXT,
            archive TEXT
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
            INSERT INTO games (title, release_year, genre, config, archive)
            VALUES (?, ?, ?, ?, ?)
        """,
            (game["title"], game["release_year"], game["genre"], game["config"], game["archive"]),
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
