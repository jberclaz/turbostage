"""
Database manager for TurboStage.

This module contains the DatabaseManager class which is responsible for
creating, initializing, and upgrading the database schema.
"""

import os
import sqlite3

from turbostage.db.constants import DB_VERSION, ORIGINAL_VERSION, SCHEMA_INDEXES, SCHEMA_TABLES


class DatabaseManager:
    """
    Database manager for TurboStage.

    This class is responsible for database creation, initialization, and upgrades.
    It provides methods to ensure the database is properly set up with the latest schema.
    """

    @staticmethod
    def create_schema(conn: sqlite3.Connection):
        """Create the initial database schema.

        This function creates the base schema for a new installation.

        Args:
            conn: An open SQLite connection
        """
        cursor = conn.cursor()

        # Create tables
        for table_sql in SCHEMA_TABLES.values():
            cursor.execute(table_sql)

        # Create indexes
        for index_sql in SCHEMA_INDEXES:
            cursor.execute(index_sql)

        # Set the database version
        cursor.execute("INSERT INTO db_version (version) VALUES (?)", (DB_VERSION,))

    @staticmethod
    def initialize_database(db_path: str):
        """Initialize a new database or upgrade an existing one.

        This function checks if the database exists and is properly initialized with tables.
        If not, it creates a new one with the latest schema.
        If it exists, it checks the version and applies any necessary migrations.

        Args:
            db_path: Path to the SQLite database file
        """
        # Create directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        db_exists = os.path.exists(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if the database is properly initialized with tables
        db_version_exists = False
        has_tables = False
        if db_exists:
            try:
                # Check if any tables exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                has_tables = len(tables) > 0
                # Check if db_version table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'")
                db_version_exists = cursor.fetchone() is not None
            except sqlite3.Error:
                # If there's an error, assume tables don't exist
                has_tables = False

        if not db_exists or not has_tables:
            # New or uninitialized database, create the schema
            DatabaseManager.create_schema(conn)
            conn.commit()
            conn.close()
            return

        # Existing database with tables
        if not db_version_exists:
            # Old database without db_version table - need migrations
            # Assume original version for databases created before version tracking
            current_version = ORIGINAL_VERSION
        else:
            # Get current version
            try:
                cursor.execute("SELECT version FROM db_version ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                current_version = row[0] if row else ORIGINAL_VERSION
            except sqlite3.Error:
                current_version = ORIGINAL_VERSION

        # Always run migrations if version doesn't match, OR if schema is missing expected columns
        needs_migration = current_version != DB_VERSION
        if not needs_migration:
            # Double-check: verify critical columns exist in local_versions
            # This handles case where version was set but migration didn't run properly
            try:
                cursor.execute("PRAGMA table_info(local_versions)")
                columns = {row[1] for row in cursor.fetchall()}
                missing_cols = []
                if "executable" not in columns:
                    missing_cols.append("executable")
                if "config_executable" not in columns:
                    missing_cols.append("config_executable")
                if "archive_type" not in columns:
                    missing_cols.append("archive_type")
                if missing_cols:
                    # Run migrations to add missing columns
                    needs_migration = True
            except sqlite3.Error:
                pass

        if needs_migration:
            try:
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
        else:
            conn.close()

    @staticmethod
    def check_and_upgrade_version(db_path: str):
        """Check and upgrade the database version if needed.

        Args:
            db_path: Path to the SQLite database file

        Returns:
            Tuple of (current_version, needs_upgrade)
        """
        if not os.path.exists(db_path):
            return None, True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT version FROM db_version ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else ORIGINAL_VERSION

            return current_version, current_version != DB_VERSION
        except sqlite3.Error as e:
            print(f"Database error during version check: {e}")
            return None, True
        finally:
            conn.close()
