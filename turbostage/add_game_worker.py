import os
import zipfile

from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage import utils
from turbostage.db.game_database import GameDatabase


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
        # Create database instance
        db = GameDatabase(self._db_path)

        # 1. check if game exists in db
        game = db.get_game_by_igdb_id(self._igdb_id)
        if game:
            game_id = game[0]  # The first column is the ID
        else:
            # 2.1 query IGDB for extra info
            details = utils.fetch_game_details(self._igdb_client, self._igdb_id)
            # 2.2 add game entry in games table
            game_id = db.insert_game_with_details(self._game_name, details, self._igdb_id)

        # Get the archive basename
        archive_basename = os.path.basename(self._game_archive)

        # 2.5 Check that this version does not already exist
        existing_versions = db.get_version_info_by_game_id(game_id)
        if existing_versions is not None:
            for version in existing_versions:
                if version[1] == self._version_name:  # version[1] is the version name
                    # Version already exists, just update the local version entry
                    version_id = version[0]  # version[0] is the version ID
                    db.insert_local_version(version_id, archive_basename)
                    self.signals.task_finished.emit()
                    return

        # 3. add game version in version table
        version_id = db.insert_game_version(
            game_id, self._version_name, self._binary, archive_basename, self._config, self._cpu_cycles
        )

        # 4. add hashes
        hashes = utils.compute_hash_for_largest_files_in_zip(self._game_archive, n=4)
        if not self._binary in [h[0] for h in hashes]:
            with zipfile.ZipFile(self._game_archive, "r") as zf:
                h = utils.compute_md5_from_zip(zf, self._binary)
                hashes.append((self._binary, 0, h))

        db.insert_multiple_hashes(version_id, hashes)

        # 5. add local version
        db.insert_local_version(version_id, archive_basename)

        self.signals.task_finished.emit()
