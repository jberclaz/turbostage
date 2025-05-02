import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from turbostage.db.populate_db import DB_VERSION


class GameDatabase:
    def __init__(self, db_file: str):
        self._db_file = db_file
        self._check_version()

    def get_version(self) -> str:
        conn = self._connection
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM db_version")
        rows = cursor.fetchall()
        conn.close()
        return rows[0][0]

    def merge_with(self, db_file):
        input_conn = sqlite3.connect(db_file)
        input_cursor = input_conn.cursor()

        output_conn = self._connection
        output_cursor = output_conn.cursor()
        try:
            game_id_mapping = GameDatabase._copy_game_table(input_cursor, output_cursor)
            output_conn.commit()
            version_id_mapping = GameDatabase._copy_versions(input_cursor, output_cursor, game_id_mapping)
            output_conn.commit()
            GameDatabase._copy_table("hashes", input_cursor, output_cursor, version_id_mapping)
            output_conn.commit()
            GameDatabase._copy_table("config_files", input_cursor, output_cursor, version_id_mapping, "type = 1")
            output_conn.commit()
        except sqlite3.Error as error:
            return f"Database error: {error}"
        except Exception as e:
            return f"Error while updating game database: {e}"
        finally:
            input_conn.close()
            output_conn.close()
            return ""

    def _check_version(self):
        version = self.get_version()
        if version != DB_VERSION:
            raise RuntimeError(
                f"Incompatible DB version {version}. Remove file at {self._db_file} and re-run the program."
            )

    @property
    def _connection(self):
        return sqlite3.connect(self._db_file)

    #
    # Game related methods
    #
    def get_all_games(self) -> List[Tuple]:
        """Retrieve all games from the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM games ORDER BY name")
            return cursor.fetchall()
        finally:
            conn.close()

    def get_game_by_id(self, game_id: int) -> Optional[Tuple]:
        """Retrieve a game by its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM games WHERE id = ?", (game_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    def get_game_by_igdb_id(self, igdb_id: int) -> Optional[Tuple]:
        """Retrieve a game by its IGDB ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM games WHERE igdb_id = ?", (igdb_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    def get_games_with_versions(self) -> List[Tuple]:
        """Retrieve all games that have associated versions."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT g.* FROM games g JOIN versions v ON g.id = v.game_id ORDER BY g.name")
            return cursor.fetchall()
        finally:
            conn.close()

    def insert_game(self, game_data: Dict[str, Any]) -> int:
        """Insert a new game into the database and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            columns = ", ".join(game_data.keys())
            placeholders = ", ".join(["?" for _ in game_data])
            query = f"INSERT INTO games ({columns}) VALUES ({placeholders})"
            cursor.execute(query, tuple(game_data.values()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def insert_game_with_details(self, game_name: str, details: Dict[str, Any], igdb_id: int) -> int:
        """Insert a game with details from IGDB and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
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
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_game(self, game_id: int, game_data: Dict[str, Any]) -> None:
        """Update an existing game in the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            set_clause = ", ".join([f"{key} = ?" for key in game_data.keys()])
            query = f"UPDATE games SET {set_clause} WHERE id = ?"
            values = list(game_data.values()) + [game_id]
            cursor.execute(query, tuple(values))
            conn.commit()
        finally:
            conn.close()

    def delete_game(self, game_id: int) -> None:
        """Delete a game and all its associated data from the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            # First delete all associated versions and their dependencies
            cursor.execute("SELECT id FROM versions WHERE game_id = ?", (game_id,))
            version_ids = [row[0] for row in cursor.fetchall()]

            for version_id in version_ids:
                cursor.execute("DELETE FROM hashes WHERE version_id = ?", (version_id,))
                cursor.execute("DELETE FROM config_files WHERE version_id = ?", (version_id,))

            cursor.execute("DELETE FROM versions WHERE game_id = ?", (game_id,))
            cursor.execute("DELETE FROM games WHERE id = ?", (game_id,))
            conn.commit()
        finally:
            conn.close()

    #
    # Version related methods
    #
    def get_versions_for_game(self, game_id: int) -> List[Tuple]:
        """Retrieve all versions for a given game."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM versions WHERE game_id = ? ORDER BY version", (game_id,))
            return cursor.fetchall()
        finally:
            conn.close()

    def get_version_by_id(self, version_id: int) -> Optional[Tuple]:
        """Retrieve a version by its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM versions WHERE id = ?", (version_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    def insert_version(self, version_data: Dict[str, Any]) -> int:
        """Insert a new version into the database and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            columns = ", ".join(version_data.keys())
            placeholders = ", ".join(["?" for _ in version_data])
            query = f"INSERT INTO versions ({columns}) VALUES ({placeholders})"
            cursor.execute(query, tuple(version_data.values()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def insert_game_version(
        self, game_id: int, version: str, executable: str, archive: str, config: str, cycles: int
    ) -> int:
        """Insert a game version with all details and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
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
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_version(self, version_id: int, version_data: Dict[str, Any]) -> None:
        """Update an existing version in the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            set_clause = ", ".join([f"{key} = ?" for key in version_data.keys()])
            query = f"UPDATE versions SET {set_clause} WHERE id = ?"
            values = list(version_data.values()) + [version_id]
            cursor.execute(query, tuple(values))
            conn.commit()
        finally:
            conn.close()

    def delete_version(self, version_id: int) -> None:
        """Delete a version and all its associated data from the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM hashes WHERE version_id = ?", (version_id,))
            cursor.execute("DELETE FROM config_files WHERE version_id = ?", (version_id,))
            cursor.execute("DELETE FROM versions WHERE id = ?", (version_id,))
            conn.commit()
        finally:
            conn.close()

    #
    # Hash related methods
    #
    def get_hashes_for_version(self, version_id: int) -> List[Tuple]:
        """Retrieve all hashes for a given version."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM hashes WHERE version_id = ?", (version_id,))
            return cursor.fetchall()
        finally:
            conn.close()

    def insert_hash(self, hash_data: Dict[str, Any]) -> int:
        """Insert a new hash into the database and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            columns = ", ".join(hash_data.keys())
            placeholders = ", ".join(["?" for _ in hash_data])
            query = f"INSERT INTO hashes ({columns}) VALUES ({placeholders})"
            cursor.execute(query, tuple(hash_data.values()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def insert_multiple_hashes(self, version_id: int, hashes: List[Tuple[str, int, str]]) -> None:
        """Insert multiple hashes for a game version."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO hashes (version_id, file_name, hash) VALUES " + ",".join(["(?, ?, ?)"] * len(hashes)),
                [item for f, _, h in hashes for item in (version_id, f, h)],
            )
            conn.commit()
        finally:
            conn.close()

    def update_hash(self, hash_id: int, hash_data: Dict[str, Any]) -> None:
        """Update an existing hash in the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            set_clause = ", ".join([f"{key} = ?" for key in hash_data.keys()])
            query = f"UPDATE hashes SET {set_clause} WHERE id = ?"
            values = list(hash_data.values()) + [hash_id]
            cursor.execute(query, tuple(values))
            conn.commit()
        finally:
            conn.close()

    def find_game_by_hash(self, file_hash: str) -> Optional[Tuple[int, int]]:
        """Find a game and version by file hash."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT v.game_id, h.version_id
                FROM hashes h
                JOIN versions v ON h.version_id = v.id
                WHERE h.hash = ?
                """,
                (file_hash,),
            )
            result = cursor.fetchone()
            return result if result else None
        finally:
            conn.close()

    def get_game_launch_info(self, game_id: int) -> Optional[Tuple]:
        """Retrieve the information needed to launch a game by its IGDB ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
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
        finally:
            conn.close()

    #
    # Config file related methods
    #
    def get_config_files_for_version(self, version_id: int, config_type: Optional[int] = None) -> List[Tuple]:
        """Retrieve all config files for a given version, optionally filtered by type."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            if config_type is not None:
                cursor.execute(
                    "SELECT * FROM config_files WHERE version_id = ? AND type = ? ORDER BY name",
                    (version_id, config_type),
                )
            else:
                cursor.execute("SELECT * FROM config_files WHERE version_id = ? ORDER BY name", (version_id,))
            return cursor.fetchall()
        finally:
            conn.close()

    def get_config_files_with_content(self, version_id: int, file_type: int) -> List[Tuple]:
        """Retrieve paths and contents of config files for a given version and type."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT path, content FROM config_files
                WHERE version_id = ? AND type = ?
                """,
                (version_id, file_type),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def insert_config_file(self, config_data: Dict[str, Any]) -> int:
        """Insert a new config file into the database and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            columns = ", ".join(config_data.keys())
            placeholders = ", ".join(["?" for _ in config_data])
            query = f"INSERT INTO config_files ({columns}) VALUES ({placeholders})"
            cursor.execute(query, tuple(config_data.values()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_config_file(self, config_id: int, config_data: Dict[str, Any]) -> None:
        """Update an existing config file in the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            set_clause = ", ".join([f"{key} = ?" for key in config_data.keys()])
            query = f"UPDATE config_files SET {set_clause} WHERE id = ?"
            values = list(config_data.values()) + [config_id]
            cursor.execute(query, tuple(values))
            conn.commit()
        finally:
            conn.close()

    def delete_config_file(self, config_id: int) -> None:
        """Delete a config file from the database."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM config_files WHERE id = ?", (config_id,))
            conn.commit()
        finally:
            conn.close()

    def insert_local_version(self, version_id: int, archive: str) -> int:
        """Insert a local version into the database and return its ID."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO local_versions (version_id, archive) VALUES (?, ?)", (version_id, archive))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    #
    # Utility methods
    #
    def execute_query(self, query: str, params: Tuple = None) -> List[Tuple]:
        """Execute a custom SQL query and return the results."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        finally:
            conn.close()

    def execute_update(self, query: str, params: Tuple = None) -> int:
        """Execute a custom SQL update query and return the number of affected rows."""
        conn = self._connection
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

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
