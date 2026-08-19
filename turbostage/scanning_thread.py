import os

from PySide6.QtCore import QThread, Signal

from turbostage import iso_utils, utils
from turbostage.db.game_database import GameDatabase


class ScanningThread(QThread):
    progress = Signal(int)
    load_games = Signal()

    def __init__(self, local_game_archives: list[str], db_path: str, games_path: str):
        super().__init__()
        self._local_game_archives = local_game_archives
        self._db_path = db_path
        self._game_path = games_path

    def run(self):
        db = GameDatabase(self._db_path)

        # Clear all local versions
        db.clear_local_versions()

        for index, game_archive in enumerate(self._local_game_archives):
            archive_path = os.path.join(self._game_path, game_archive)

            # Determine archive type and compute hashes accordingly
            if iso_utils.is_iso_file(archive_path):
                archive_type = "iso"
                hashes = iso_utils.compute_hash_for_largest_files_in_iso(archive_path, 4)
            else:
                archive_type = "zip"
                hashes = utils.compute_hash_for_largest_files_in_zip(archive_path, 4)

            # Extract just the hash values from the tuples
            hash_values = [h[2] for h in hashes]
            # Use GameDatabase to find game by hashes
            version_id = db.find_game_by_hashes(hash_values)
            if version_id is not None:
                if archive_type == "iso":
                    hashes.extend(iso_utils.compute_hashes_for_executables_in_iso(archive_path))
                else:
                    hashes.extend(utils.compute_hashes_for_executables_in_zip(archive_path))
                local_executable, local_config_executable = db.resolve_local_executables(version_id, hashes)
                requires_install = db.get_version_requires_install(version_id)
                db.add_local_game_version(
                    version_id, game_archive, local_executable, local_config_executable,
                    archive_type, requires_install,
                )
            self.progress.emit(index + 1)

        self.load_games.emit()
