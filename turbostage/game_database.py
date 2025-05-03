import os
import queue
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from turbostage.db.populate_db import DB_VERSION

# Indexes are now created during schema initialization and migration


class ConnectionPool:
    """A connection pool for SQLite database connections.

    This class manages a pool of SQLite connections to improve performance
    by reusing connections instead of creating new ones for each query.
    """

    def __init__(self, db_file: str, max_connections: int = 5, timeout: float = 30.0):
        """Initialize the connection pool.

        Args:
            db_file: Path to the SQLite database file
            max_connections: Maximum number of connections to keep in the pool
            timeout: Timeout for SQLite connection operations
        """
        self._db_file = db_file
        self._max_connections = max_connections
        self._timeout = timeout
        self._pool = queue.Queue(maxsize=max_connections)
        self._active_connections = 0
        self._lock = threading.Lock()

    def get_connection(self, read_only: bool = False) -> sqlite3.Connection:
        """Get a connection from the pool or create a new one if needed.

        Args:
            read_only: If True, optimize the connection for read-only operations

        Returns:
            A SQLite connection
        """
        try:
            # Try to get a connection from the pool
            connection = self._pool.get_nowait()
            return connection
        except queue.Empty:
            # Pool is empty, create a new connection if under the limit
            with self._lock:
                if self._active_connections < self._max_connections:
                    self._active_connections += 1
                    connection = sqlite3.connect(
                        self._db_file,
                        timeout=self._timeout,
                    )
                    # Configure connection based on read_only flag
                    if read_only:
                        connection.execute("PRAGMA query_only = ON")
                    connection.execute("PRAGMA foreign_keys = ON")
                    return connection
                else:
                    # Wait for a connection to be returned to the pool
                    try:
                        return self._pool.get(timeout=self._timeout)
                    except queue.Empty:
                        raise RuntimeError("Timed out waiting for a database connection")

    def return_connection(self, connection: sqlite3.Connection) -> None:
        """Return a connection to the pool.

        Args:
            connection: The SQLite connection to return to the pool
        """
        # Reset connection state before returning to pool
        connection.rollback()  # Ensure no transactions are pending

        try:
            self._pool.put_nowait(connection)
        except queue.Full:
            # Pool is full, close the connection
            with self._lock:
                self._active_connections -= 1
                connection.close()

    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                    self._active_connections -= 1
                except queue.Empty:
                    break
            # The pool is now empty


class GameDatabase:
    def __init__(self, db_file: str):
        self._db_file = db_file
        self._connection_pool = ConnectionPool(db_file)

        # Create the database and indexes if the file doesn't exist
        db_exists = os.path.exists(db_file)

        # Initialize database schema if this is a new database
        if db_exists:
            # Enable WAL mode for better concurrent access
            with self.transaction() as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                # Foreign keys already enabled in transaction context

            # Check version and run migrations if needed
            self._check_version()

    def get_version(self) -> str:
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM db_version")
            rows = cursor.fetchall()
            return rows[0][0] if rows else "unknown"

    def merge_with(self, db_file):
        input_conn = sqlite3.connect(db_file)
        input_cursor = input_conn.cursor()

        try:
            with self.transaction() as output_conn:
                output_cursor = output_conn.cursor()

                # The transaction context manager will handle commit/rollback automatically
                game_id_mapping = GameDatabase._copy_game_table(input_cursor, output_cursor)
                version_id_mapping = GameDatabase._copy_versions(input_cursor, output_cursor, game_id_mapping)
                GameDatabase._copy_table("hashes", input_cursor, output_cursor, version_id_mapping)
                GameDatabase._copy_table("config_files", input_cursor, output_cursor, version_id_mapping, "type = 1")

                # No explicit commit needed - handled by transaction context manager
                return ""
        except sqlite3.Error as error:
            return f"Database error: {error}"
        except Exception as e:
            return f"Error while updating game database: {e}"
        finally:
            input_conn.close()

    def _check_version(self):
        try:
            version = self.get_version()
            if version != DB_VERSION:
                # Import migrations module here to avoid circular imports
                from turbostage.db.migrations import migrate_database

                # Open a direct connection for migration (outside the connection pool)
                # to avoid transaction issues during schema changes
                with sqlite3.connect(self._db_file) as conn:
                    migrate_database(conn, version, DB_VERSION)

                    # Ensure the version is updated
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM db_version")
                    cursor.execute("INSERT INTO db_version (version) VALUES (?)", (DB_VERSION,))
                    conn.commit()

                print(f"Successfully migrated database from version {version} to {DB_VERSION}")
        except sqlite3.OperationalError as e:
            # Database might be new or not have the version table yet
            # This will be handled by the initialization code
            print(f"Database operation error during version check: {e}")
            pass

    def get_connection(self):
        """Get a raw connection to the database from the connection pool.

        DEPRECATED: This method is being phased out in favor of transaction() and
        read_only_transaction() context managers.

        This method returns a direct connection to the SQLite database without
        any transaction management. It should be used with caution and only in
        cases where you need complete control over the transaction lifecycle.

        For most operations, use transaction() or read_only_transaction() instead,
        which provide proper transaction management with automatic commit/rollback.

        WARNING: When using this method, you are responsible for returning the connection
        to the pool by calling connection_pool.return_connection(conn) to avoid connection leaks.

        Returns:
            A raw SQLite connection object from the connection pool
        """
        return self._connection_pool.get_connection(read_only=False)

    def transaction(self):
        """Create a transaction context manager for safe database operations.

        This context manager obtains a database connection from the connection pool
        for operations that modify the database. The transaction is automatically committed
        when the context is exited normally, or rolled back if an exception occurs.
        The connection is returned to the pool after use.

        Usage:
            with db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
                # On successful completion, transaction is committed
                # On exception, transaction is rolled back automatically

        Returns:
            A context manager that handles transaction lifecycle
        """

        class TransactionContextManager:
            def __init__(self, connection_pool):
                self.connection_pool = connection_pool
                self.conn = None

            def __enter__(self):
                self.conn = self.connection_pool.get_connection(read_only=False)
                return self.conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.conn:
                    if exc_type is not None:
                        # An exception occurred, roll back
                        self.conn.rollback()
                    else:
                        # No exception, commit the transaction
                        self.conn.commit()

                    # Return the connection to the pool instead of closing it
                    self.connection_pool.return_connection(self.conn)

                return False  # Don't suppress exceptions

        return TransactionContextManager(self._connection_pool)

    def read_only_transaction(self):
        """Create a read-only transaction context manager for database operations.

        This context manager obtains a database connection from the connection pool
        optimized for read-only operations. It uses SQLite's "read uncommitted" isolation level
        for better performance and does not create a write transaction, which allows for better concurrency.
        The connection is returned to the pool after use.

        Usage:
            with db.read_only_transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ...")
                # No commit or rollback needed for read-only operations

        Returns:
            A context manager that handles read-only connection lifecycle
        """

        class ReadOnlyTransactionContextManager:
            def __init__(self, connection_pool):
                self.connection_pool = connection_pool
                self.conn = None

            def __enter__(self):
                self.conn = self.connection_pool.get_connection(read_only=True)
                return self.conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.conn:
                    # Return the connection to the pool instead of closing it
                    self.connection_pool.return_connection(self.conn)

                return False  # Don't suppress exceptions

        return ReadOnlyTransactionContextManager(self._connection_pool)

    #
    # Game related methods
    #

    def get_game_by_igdb_id(self, igdb_id: int) -> Optional[Tuple]:
        """Retrieve a game by its IGDB ID."""
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM games WHERE igdb_id = ?", (igdb_id,))
            return cursor.fetchone()

    def get_game_details_by_igdb_id(self, igdb_id: int) -> Optional[Tuple[str, str, str, str, str]]:
        """Retrieve game details (release_date, genre, summary, publisher, cover_url) by IGDB ID.

        Args:
            igdb_id: The IGDB ID of the game

        Returns:
            A tuple containing (release_date, genre, summary, publisher, cover_url) or None if not found
        """
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT release_date, genre, summary, publisher, cover_url
                FROM games
                WHERE igdb_id = ?
                """,
                (igdb_id,),
            )
            return cursor.fetchone()

    def update_game_details(
        self, igdb_id: int, summary: str, release_date: str, genre: str, publisher: str, cover_url: str
    ) -> None:
        """Update game details for a game with the given IGDB ID.

        Args:
            igdb_id: The IGDB ID of the game to update
            summary: Game summary text
            release_date: Formatted release date
            genre: Game genre(s)
            publisher: Game publisher
            cover_url: URL to game cover image
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE games
                SET summary = ?, release_date = ?, genre = ?, publisher = ?, cover_url = ?
                WHERE igdb_id = ?
                """,
                (summary, release_date, genre, publisher, cover_url, igdb_id),
            )

    def insert_game_with_details(self, game_name: str, details: Dict[str, Any], igdb_id: int) -> int:
        """Insert a game with details from IGDB and return its ID."""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO games (title, summary, release_date, genre, publisher, igdb_id, cover_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_name,
                    details["summary"],
                    details["release_date"],
                    details["genres"],
                    details["publisher"],
                    igdb_id,
                    details["cover"],
                ),
            )
            return cursor.lastrowid

    def delete_game_by_igdb_id(self, igdb_id: int) -> None:
        """Delete a game by its IGDB ID and all its associated data from the database.

        Args:
            igdb_id: The IGDB ID of the game to delete
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Get the internal game ID first
            cursor.execute("SELECT id FROM games WHERE igdb_id = ?", (igdb_id,))
            row = cursor.fetchone()
            if row:
                internal_id = row[0]

                # Delete all associated versions and their dependencies in a single transaction
                # Get all version IDs
                cursor.execute("SELECT id FROM versions WHERE game_id = ?", (internal_id,))
                version_ids = [row[0] for row in cursor.fetchall()]

                # Use parameterized queries for batch operations if possible
                if version_ids:
                    version_placeholders = ",".join(["?"] * len(version_ids))

                    # Delete related records in dependent tables
                    cursor.execute(f"DELETE FROM hashes WHERE version_id IN ({version_placeholders})", version_ids)
                    cursor.execute(
                        f"DELETE FROM config_files WHERE version_id IN ({version_placeholders})", version_ids
                    )
                    cursor.execute(
                        f"DELETE FROM local_versions WHERE version_id IN ({version_placeholders})", version_ids
                    )

                # Delete the versions and game
                cursor.execute("DELETE FROM versions WHERE game_id = ?", (internal_id,))
                cursor.execute("DELETE FROM games WHERE id = ?", (internal_id,))

            # Transaction context manager handles commit and rollback automatically

    #
    # Version related methods
    #

    def insert_game_version(
        self, game_id: int, version: str, executable: str, archive: str, config: str, cycles: int
    ) -> int:
        """Insert a game version with all details and return its ID."""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO versions (game_id, version, executable, archive, config, cycles)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    version,
                    executable,
                    archive,
                    config,
                    cycles,
                ),
            )
            return cursor.lastrowid

    #
    # Hash related methods
    #

    def insert_multiple_hashes(self, version_id: int, hashes: List[Tuple[str, int, str]]) -> None:
        """Insert multiple hashes for a game version."""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO hashes (version_id, file_name, hash) VALUES " + ",".join(["(?, ?, ?)"] * len(hashes)),
                [item for f, _, h in hashes for item in (version_id, f, h)],
            )

    def get_game_launch_info(self, game_id: int) -> Optional[Tuple]:
        """Retrieve the information needed to launch a game by its IGDB ID."""
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.executable, lv.archive, v.config, v.cycles, v.id
                FROM games g
                JOIN versions v ON g.id = v.game_id
                JOIN local_versions lv ON v.id = lv.version_id
                WHERE g.igdb_id = ?
                """,
                (game_id,),
            )
            return cursor.fetchone()

    def get_version_info_by_game_id(self, game_id: int) -> Optional[Tuple]:
        """Retrieve version information for a game by its IGDB ID.

        Args:
            game_id: The IGDB ID of the game

        Returns:
            A tuple containing (version_id, executable, config, cycles, archive) or None if not found
        """
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.id, v.executable, v.config, v.cycles, lv.archive
                FROM versions v
                JOIN local_versions lv ON v.id = lv.version_id
                JOIN games g ON v.game_id = g.id
                WHERE g.igdb_id = ?
                """,
                (game_id,),
            )
            return cursor.fetchone()

    def get_config_files_metadata(self, version_id: int, file_type: int) -> List[Tuple]:
        """Retrieve metadata for config files of a specified type.

        Args:
            version_id: The version ID to get config files for
            file_type: The type of config files to retrieve (e.g., CONFIG or SAVEGAME)

        Returns:
            A list of tuples containing (path, name, id) for each file
        """
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT path, name, id FROM config_files
                WHERE version_id = ? AND type = ?
                ORDER BY name
                """,
                (version_id, file_type),
            )
            return cursor.fetchall()

    def get_games_with_local_versions(self) -> List[Tuple]:
        """Retrieve all games that have local versions installed.

        Returns:
            A list of tuples containing (igdb_id, title, release_date, genre, version)
        """
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT g.igdb_id, g.title, g.release_date, g.genre, v.version
                FROM games g JOIN versions v ON g.id = v.game_id
                JOIN local_versions lv ON v.id = lv.version_id
                ORDER BY g.title
                """
            )
            return cursor.fetchall()

    def get_version_details_by_game_id(self, game_id: int) -> Optional[Tuple]:
        """Retrieve detailed version information for a game by its IGDB ID.

        Args:
            game_id: The IGDB ID of the game

        Returns:
            A tuple containing (version_id, executable, config, cycles, archive, version_name)
            or None if not found
        """
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.id, v.executable, v.config, v.cycles, v.archive, v.version
                FROM versions v
                JOIN games g ON v.game_id = g.id
                JOIN local_versions lv ON v.id = lv.version_id
                WHERE g.igdb_id = ?
                """,
                (game_id,),
            )
            return cursor.fetchone()

    def find_setup_executables(self, version_id: int) -> list[str]:
        """Find setup executable files for a game version.

        Args:
            version_id: The version ID to find setup executables for

        Returns:
            A list of executable filenames that match setup patterns
        """
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT h.file_name
                FROM hashes h
                WHERE h.version_id = ? AND lower(h.file_name) LIKE '%setup%exe'
                """,
                (version_id,),
            )
            return [row[0] for row in cursor.fetchall()]

    #
    # Config file related methods
    #

    def get_config_files_with_content(self, version_id: int, file_type: int) -> list[tuple]:
        """Retrieve paths and contents of config files for a given version and type."""
        with self.read_only_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT path, content FROM config_files
                WHERE version_id = ? AND type = ?
                """,
                (version_id, file_type),
            )
            return cursor.fetchall()

    def add_extra_files(self, files: Dict[str, bytes], version_id: int, file_type: int) -> None:
        """Add or update extra files (config files, save games) in the database.

        Args:
            files: Dictionary mapping file paths to their content as bytes
            version_id: The version ID to associate these files with
            file_type: The type of files (e.g., CONFIG or SAVEGAME)
        """
        if not files:
            return

        with self.transaction() as conn:
            cursor = conn.cursor()

            # First, get all existing files of this type for this version to reduce lookups
            cursor.execute(
                """
                SELECT id, path FROM config_files
                WHERE version_id = ? AND type = ?
                """,
                (version_id, file_type),
            )
            existing_files = {path: file_id for file_id, path in cursor.fetchall()}

            # Prepare batch updates and inserts
            updates = []
            inserts = []

            for file_path, content in files.items():
                base_name = os.path.basename(file_path)

                if file_path in existing_files:  # File exists, update it
                    updates.append((content, base_name, existing_files[file_path]))
                else:  # File doesn't exist, insert it
                    inserts.append((version_id, file_path, content, file_type, base_name))

            # Execute batch updates
            if updates:
                cursor.executemany(
                    """
                    UPDATE config_files
                    SET content = ?, name = ?
                    WHERE id = ?
                    """,
                    updates,
                )

            # Execute batch inserts
            if inserts:
                cursor.executemany(
                    """
                    INSERT INTO config_files (version_id, path, content, type, name)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    inserts,
                )

            # Transaction context manager handles commit and rollback automatically

    def insert_local_version(self, version_id: int, archive: str) -> int:
        """Insert a local version into the database and return its ID."""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO local_versions (version_id, archive) VALUES (?, ?)", (version_id, archive))
            return cursor.lastrowid

    def clear_local_versions(self) -> None:
        """Remove all local game versions from the database."""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM local_versions")

    def find_game_by_hashes(self, hashes: List[str]) -> Optional[int]:
        """Find a game version by matching multiple file hashes.

        Args:
            hashes: A list of MD5 hash strings to check against the database

        Returns:
            The version_id if a match is found, None otherwise
        """
        if not hashes:
            return None

        with self.read_only_transaction() as conn:
            cursor = conn.cursor()

            # Use parameter substitution to prevent SQL injection
            placeholders = ",".join(["?"] * len(hashes))
            query = f"""
                SELECT version_id, COUNT(*) as match_count
                FROM hashes
                WHERE hash IN ({placeholders})
                GROUP BY version_id
                ORDER BY match_count DESC
                LIMIT 1
            """
            cursor.execute(query, hashes)
            result = cursor.fetchone()
            return result[0] if result else None

    #
    # Utility methods
    #

    @staticmethod
    def _get_table_columns(cursor, table_name):
        """Retrieve column names of a table."""
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [info[1] for info in cursor.fetchall()]

    @staticmethod
    def _copy_table(
        table_name: str,
        input_cursor: sqlite3.Cursor,
        output_cursor: sqlite3.Cursor,
        version_id_mapping: dict,
        conditions: str = None,
    ):
        columns = GameDatabase._get_table_columns(input_cursor, table_name)
        input_version_ids = list(version_id_mapping.keys())
        placeholders = ",".join(["?" for _ in input_version_ids])
        query = f"SELECT * FROM {table_name} WHERE version_id IN ({placeholders})"
        if conditions is not None:
            query += f" AND {conditions}"
        input_cursor.execute(query, input_version_ids)
        input_rows = input_cursor.fetchall()

        insert_columns = [col for col in columns if col != "id"]
        value_placeholders = ",".join(["?" for _ in insert_columns])
        insert_query = f"INSERT INTO {table_name} ({','.join(insert_columns)}) VALUES ({value_placeholders})"

        inserted_row_count = 0
        version_id_idx = columns.index("version_id")

        for row in input_rows:
            input_version_id = row[version_id_idx]
            if input_version_id not in version_id_mapping:
                continue

            row_data = [
                version_id_mapping[input_version_id] if col == "version_id" else row[columns.index(col)]
                for col in insert_columns
            ]
            output_cursor.execute(insert_query, tuple(row_data))
            inserted_row_count += 1

        print(f"Processed {len(input_rows)} {table_name} rows from input database.")
        print(f"Inserted {inserted_row_count} new {table_name} rows into output database.")

    @staticmethod
    def _copy_versions(input_cursor: sqlite3.Cursor, output_cursor: sqlite3.Cursor, game_id_mapping: dict) -> dict:
        input_game_ids = list(game_id_mapping.keys())
        placeholders = ",".join(["?" for _ in input_game_ids])
        input_cursor.execute(f"SELECT * FROM versions WHERE game_id IN ({placeholders})", input_game_ids)
        input_version_rows = input_cursor.fetchall()

        version_columns = GameDatabase._get_table_columns(input_cursor, "versions")
        insert_columns = [col for col in version_columns if col != "id"]
        version_placeholders = ",".join(["?" for _ in insert_columns])
        version_insert_query = f"INSERT INTO versions ({','.join(insert_columns)}) VALUES ({version_placeholders})"

        version_id_mapping = {}
        inserted_version_count = 0
        game_id_idx = version_columns.index("game_id")
        for row in input_version_rows:
            input_game_id = row[game_id_idx]
            input_version_id = row[version_columns.index("id")]
            if input_game_id not in game_id_mapping:
                raise RuntimeError(f"Game ID '{input_game_id}' not found.")

            # Prepare row data, excluding 'id' and updating 'game_id'
            row_data = [
                game_id_mapping[input_game_id] if col == "game_id" else row[version_columns.index(col)]
                for col in insert_columns
            ]
            output_cursor.execute(version_insert_query, row_data)
            inserted_version_count += 1
            new_version_id = output_cursor.lastrowid
            version_id_mapping[input_version_id] = new_version_id

        print(f"Processed {len(input_version_rows)} version rows from input database.")
        print(f"Inserted {inserted_version_count} new version rows into output database.")

        return version_id_mapping

    def close(self):
        """Close the database connection pool.

        This method should be called when the database is no longer needed
        to properly clean up resources and close all connections.
        """
        if hasattr(self, "_connection_pool"):
            self._connection_pool.close_all()

    def __del__(self):
        """Destructor to ensure connection pool is closed when object is garbage collected."""
        self.close()

    @staticmethod
    def _copy_game_table(input_cursor: sqlite3.Cursor, output_cursor: sqlite3.Cursor) -> dict:

        columns = GameDatabase._get_table_columns(input_cursor, "games")
        if "igdb_id" not in columns:
            raise ValueError("Input database 'games' table does not have an 'igdb_id' column.")

        input_cursor.execute(f"SELECT * FROM games")
        input_rows = input_cursor.fetchall()

        # Get existing igdb_ids in output database
        output_cursor.execute("SELECT igdb_id FROM games")
        existing_igdb_ids = set(row[0] for row in output_cursor.fetchall())

        # Prepare insert query
        insert_columns = columns[: columns.index("id")] + columns[columns.index("id") + 1 :]
        placeholders = ",".join(["?" for _ in insert_columns])
        insert_query = f"INSERT INTO games ({','.join(insert_columns)}) VALUES ({placeholders})"

        # Compare and insert new rows
        inserted_count = 0
        game_id_mapping = {}
        for row in input_rows:
            igdb_id = row[columns.index("igdb_id")]
            if igdb_id in existing_igdb_ids:
                continue
            input_id = row[columns.index("id")]
            insert_row = row[: columns.index("id")] + row[columns.index("id") + 1 :]
            output_cursor.execute(insert_query, insert_row)
            inserted_count += 1
            existing_igdb_ids.add(igdb_id)  # Update set to avoid duplicates
            output_game_id = output_cursor.lastrowid
            game_id_mapping[input_id] = output_game_id

        print(f"Processed {len(input_rows)} rows from input database.")
        print(f"Inserted {inserted_count} new rows into output database.")
        return game_id_mapping
