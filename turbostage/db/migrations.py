"""
Database migration system for TurboStage.

This module handles database schema migrations, allowing safe upgrades
between different database versions without data loss or requiring users
to delete their database files.
"""

import sqlite3
from typing import Callable, Dict, List, Tuple

# Migration version format: major.minor.patch
# Each migration function handles the upgrade from the previous version to this version
MIGRATIONS: Dict[str, Callable[[sqlite3.Connection], None]] = {}


def migration(version: str) -> Callable:
    """Decorator to register a migration function for a specific version.

    Args:
        version: The version this migration upgrades to

    Returns:
        Decorator function
    """

    def decorator(func: Callable[[sqlite3.Connection], None]) -> Callable:
        MIGRATIONS[version] = func
        return func

    return decorator


def get_ordered_migrations(from_version: str, to_version: str) -> List[Tuple[str, Callable]]:
    """Get a list of migration functions to execute in order.

    Args:
        from_version: Starting version
        to_version: Target version

    Returns:
        List of (version, migration_function) tuples to apply in order
    """
    # Convert versions to tuples of integers for comparison
    from_parts = tuple(int(p) for p in from_version.split("."))
    to_parts = tuple(int(p) for p in to_version.split("."))

    if from_parts > to_parts:
        raise ValueError(f"Cannot downgrade from {from_version} to {to_version}")

    # Get all migrations that should be applied
    applicable_migrations = []
    for version, func in sorted(
        MIGRATIONS.items(),
        key=lambda x: tuple(int(p) for p in x[0].split(".")),
    ):
        version_parts = tuple(int(p) for p in version.split("."))
        if from_parts < version_parts <= to_parts:
            applicable_migrations.append((version, func))

    return applicable_migrations


def migrate_database(db_conn: sqlite3.Connection, from_version: str, to_version: str) -> None:
    """Apply all necessary migrations to upgrade a database from one version to another.

    Args:
        db_conn: SQLite database connection
        from_version: Current database version
        to_version: Target database version
    """
    migrations = get_ordered_migrations(from_version, to_version)
    if not migrations:
        # No migrations needed or available
        return

    # Apply each migration in order
    for version, migration_func in migrations:
        print(f"Applying migration to version {version}...")
        migration_func(db_conn)

        # Update the version in the database after each successful migration
        cursor = db_conn.cursor()
        cursor.execute("UPDATE db_version SET version = ? WHERE id = 1", (version,))
        db_conn.commit()

    print(f"Successfully migrated database from version {from_version} to {to_version}")


# Define migration functions for each version change


@migration("0.5.1")
def migrate_to_0_5_1(conn: sqlite3.Connection) -> None:
    """Migration to version 0.5.1.

    This adds the 'name' column to the config_files table.
    """
    cursor = conn.cursor()

    # Add name column to config_files table
    cursor.execute("ALTER TABLE config_files ADD COLUMN name TEXT")

    # Update name field with basename of path for existing rows
    cursor.execute(
        """
        UPDATE config_files
        SET name = SUBSTR(path, INSTR(path, '/') + 1)
        WHERE name IS NULL AND INSTR(path, '/') > 0
    """
    )

    # For paths without a slash, use the whole path
    cursor.execute(
        """
        UPDATE config_files
        SET name = path
        WHERE name IS NULL
    """
    )


@migration("0.6.0")
def migrate_to_0_6_0(conn: sqlite3.Connection) -> None:
    """Migration to version 0.6.0.

    Adds indexes for performance optimization.
    """
    cursor = conn.cursor()

    # Add indexes to frequently searched columns
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_igdb_id ON games(igdb_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_game_id ON versions(game_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hashes_version_id ON hashes(version_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hashes_hash ON hashes(hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_files_version_id ON config_files(version_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_files_version_path ON config_files(version_id, path, type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_local_versions_version_id ON local_versions(version_id)")


@migration("0.7.0")
def migrate_to_0_7_0(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE versions ADD COLUMN config_executable TEXT")


@migration("0.8.0")
def migrate_to_0_8_0(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE new_games (igdb_id INTEGER PRIMARY KEY, title TEXT, release_date INTEGER, genre TEXT, summary TEXT, publisher TEXT, cover_url TEXT)"
    )
    cursor.execute(
        "INSERT INTO new_games (igdb_id, title, release_date, genre, summary, publisher, cover_url) SELECT igdb_id, title, release_date, genre, summary, publisher, cover_url FROM games"
    )
    cursor.execute("UPDATE versions SET game_id = (SELECT igdb_id FROM games WHERE games.id = versions.game_id)")
    cursor.execute("DROP TABLE games")
    cursor.execute("ALTER TABLE new_games RENAME TO games")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_igdb_id ON games(igdb_id)")


@migration("0.9.0")
def migrate_to_0_9_0(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE games ADD COLUMN developer TEXT")
    cursor.execute("ALTER TABLE games ADD COLUMN screenshot_urls TEXT")
    cursor.execute("ALTER TABLE games ADD COLUMN rating INTEGER")
