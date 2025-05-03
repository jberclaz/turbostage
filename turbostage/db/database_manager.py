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

        This function checks if the database exists. If not, it creates a new one with the latest schema.
        If it exists, it checks the version and applies any necessary migrations.

        Args:
            db_path: Path to the SQLite database file
        """
        db_exists = os.path.exists(db_path)

        conn = sqlite3.connect(db_path)

        if not db_exists:
            # New database, create the schema
            DatabaseManager.create_schema(conn)
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
