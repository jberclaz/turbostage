import sys

game_data = [
    {"title": "The Secret of Monkey Island", "release_year": 1990, "genre": "Adventure"},
    {"title": "Need for Speed", "release_year": 1994, "genre": "Racing"},
    {"title": "DOOM", "release_year": 1993, "genre": "Shooter"},
    {"title": "SimCity 2000", "release_year": 1993, "genre": "Simulation"},
    {"title": "Prince of Persia", "release_year": 1989, "genre": "Platformer"},
]

import sqlite3


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
            INSERT INTO games (title, release_year, genre)
            VALUES (?, ?, ?)
        """,
            (game["title"], game["release_year"], game["genre"]),
        )

    conn.commit()
    conn.close()
    print("Database populated successfully.")


if __name__ == "__main__":
    database_path = "games.db"
    initialize_database(database_path)
    populate_database(database_path, game_data)
