import os
import sqlite3
import zipfile

from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage import utils


class WorkerSignals(QObject):
    task_finished = Signal()


class AddGameWorker(QRunnable):
    def __init__(
        self,
        game_name: str,
        version_name: str,
        igdb_id: int,
        game_archive: str,
        binary: str,
        cpu_cycles: int,
        config: str,
        db_path: str,
        igdb_client,
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self._game_name = game_name
        self._version_name = version_name
        self._igdb_id = igdb_id
        self._game_archive = game_archive
        self._binary = binary
        self._cpu_cycles = cpu_cycles
        self._config = config
        self._db_path = db_path
        self._igdb_client = igdb_client

    def run(self):
        # 1. check if game exists in db
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM games WHERE igdb_id = ?", (self._igdb_id,))
        rows = cursor.fetchall()
        if len(rows) > 0:
            game_id = rows[0][0]
        else:
            # 2.1 query IGDB for extra info
            details = utils.fetch_game_details(self._igdb_client, self._igdb_id)
            # 2.2 add game entry in games table
            cursor.execute(
                """
                INSERT INTO games (title, summary, release_date, genre, publisher, igdb_id, cover_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self._game_name,
                    details["summary"],
                    details["release_date"],
                    details["genres"],
                    details["publisher"],
                    self._igdb_id,
                    details["cover"],
                ),
            )
            game_id = cursor.lastrowid
        # 2.5 TODO: check that this version does not already exist.
        # 3. add game version in version table
        cursor.execute(
            """
            INSERT INTO versions (game_id, version, executable, archive, config, cycles)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                self._version_name,
                self._binary,
                os.path.basename(self._game_archive),
                self._config,
                self._cpu_cycles,
            ),
        )
        version_id = cursor.lastrowid
        # 4. add hashes
        hashes = utils.compute_hash_for_largest_files_in_zip(self._game_archive, n=4)
        if not self._binary in [h[0] for h in hashes]:
            with zipfile.ZipFile(self._game_archive, "r") as zf:
                h = utils.compute_md5_from_zip(zf, self._binary)
                hashes.append((self._binary, 0, h))
        cursor.execute(
            "INSERT INTO hashes (version_id, file_name, hash) VALUES " + ",".join(["(?, ?, ?)"] * len(hashes)),
            [item for f, _, h in hashes for item in (version_id, f, h)],
        )
        # 5. add local version
        cursor.execute(
            "INSERT INTO local_versions (version_id, archive) VALUES (?, ?)",
            (version_id, os.path.basename(self._game_archive)),
        )
        conn.commit()
        conn.close()
        self.signals.task_finished.emit()
