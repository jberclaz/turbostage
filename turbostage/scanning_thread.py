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
                # Find the actual executable paths in the user's archive
                # by matching hashes from the versions table
                local_executable, local_config_executable = self._find_local_executables(db, version_id, hashes)
                db.add_local_game_version(
                    version_id, game_archive, local_executable, local_config_executable, archive_type
                )
            self.progress.emit(index + 1)

        self.load_games.emit()

    def _find_local_executables(
        self, db: GameDatabase, version_id: int, local_hashes: list[tuple[str, int, str]]
    ) -> tuple[str | None, str | None]:
        """Find the actual executable paths in the user's archive by hash matching.

        Args:
            db: GameDatabase instance
            version_id: The matched version ID
            local_hashes: List of (file_path, size, hash) tuples from the user's zip

        Returns:
            Tuple of (executable_path, config_executable_path) as found in user's archive
        """
        # Get version info with expected executables
        version_info = db.get_version_by_version_id(version_id)
        if not version_info:
            return None, None

        expected_executable = version_info.executable
        expected_config_executable = version_info.config_executable

        # Get all hashes for this version from the database
        version_hashes = db.get_version_hashes(version_id)  # List of (file_name, hash)
        version_hash_map = {h: fn for fn, h in version_hashes}

        # Create a map from hash to local file path
        local_hash_map = {h: fn for fn, _, h in local_hashes}

        # Find the actual executable path by hash
        local_executable = None
        local_config_executable = None

        if expected_executable:
            # Find the hash of the expected executable in the version hashes
            expected_exec_hash = version_hash_map.get(expected_executable)
            if expected_exec_hash:
                # Find which local file has this hash
                local_executable = local_hash_map.get(expected_exec_hash)

        if expected_config_executable:
            # Find the hash of the expected config executable
            expected_config_hash = version_hash_map.get(expected_config_executable)
            if expected_config_hash:
                local_config_executable = local_hash_map.get(expected_config_hash)

        return local_executable, local_config_executable
