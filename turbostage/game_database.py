import sqlite3

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

    def add_local_game(self, version_id: int, game_archive_name: str) -> int:
        """
        Add a new game to the local version database
        :param version_id: game version id
        :param game_archive_name: game archive name (without path)
        :return: 1 if successfully added and 0 if the game already exists
        """
        conn = self._connection
        cursor = conn.cursor()

        cursor.execute("SELECT count(*) FROM local_versions WHERE version_id = ?", (version_id,))
        rows = cursor.fetchall()
        if rows[0][0] > 0:
            conn.close()
            return 0

        cursor.execute(
            "INSERT INTO local_versions (version_id, archive) VALUES (?, ?)", (version_id, game_archive_name)
        )
        conn.commit()
        conn.close()
        return 1

    def _check_version(self):
        version = self.get_version()
        if version != DB_VERSION:
            raise RuntimeError(
                f"Incompatible DB version {version}. Remove file at {self._db_file} and re-run the program."
            )

    @property
    def _connection(self):
        return sqlite3.connect(self._db_file)

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
