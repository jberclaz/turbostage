"""
Database constants for TurboStage.

This module contains database-related constants such as version numbers
and schema definitions.
"""

# Current database version - used for new installations and migrations
DB_VERSION = "0.11.0"

# Original schema version - for reference
ORIGINAL_VERSION = "0.5.0"

# Database schema tables definition
SCHEMA_TABLES = {
    "games": """
        CREATE TABLE IF NOT EXISTS games (
            igdb_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            release_date INTEGER,
            genre TEXT,
            summary TEXT,
            publisher TEXT,
            developer TEXT,
            cover_url TEXT,
            screenshot_urls TEXT,
            rating INTEGER,
            last_updated INTEGER
        );
    """,
    "versions": """
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            version TEXT,
            executable TEXT,
            config_executable TEXT,
            config TEXT,
            cycles INTEGER DEFAULT 0,
            source TEXT DEFAULT 'local',
            download_url TEXT
        );
    """,
    "hashes": """
        CREATE TABLE IF NOT EXISTS hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            file_name TEXT,
            hash TEXT
        );
    """,
    "local_versions": """
        CREATE TABLE IF NOT EXISTS local_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER UNIQUE NOT NULL,
            archive TEXT,
            executable TEXT,
            config_executable TEXT,
            archive_type TEXT DEFAULT 'zip',
            requires_install INTEGER DEFAULT 0
        );
    """,
    "installations": """
        CREATE TABLE IF NOT EXISTS installations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER UNIQUE NOT NULL,
            install_path TEXT NOT NULL,
            installed BOOLEAN DEFAULT FALSE,
            install_date INTEGER,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        );
    """,
    "config_files": """
        CREATE TABLE IF NOT EXISTS config_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            path TEXT,
            content BLOB,
            name TEXT
        )
    """,
    "db_version": """
        CREATE TABLE IF NOT EXISTS db_version (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          version TEXT NOT NULL
        );
    """,
}

# Database schema indexes definition
SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_games_igdb_id ON games(igdb_id)",
    "CREATE INDEX IF NOT EXISTS idx_versions_game_id ON versions(game_id)",
    "CREATE INDEX IF NOT EXISTS idx_hashes_version_id ON hashes(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_hashes_hash ON hashes(hash)",
    "CREATE INDEX IF NOT EXISTS idx_config_files_version_id ON config_files(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_config_files_version_path ON config_files(version_id, path, type)",
    "CREATE INDEX IF NOT EXISTS idx_local_versions_version_id ON local_versions(version_id)",
    "CREATE INDEX IF NOT EXISTS idx_installations_version_id ON installations(version_id)",
]
