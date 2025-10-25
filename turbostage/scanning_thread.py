import os

from PySide6.QtCore import QThread, Signal

from turbostage import utils
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
            hashes = utils.compute_hash_for_largest_files_in_zip(os.path.join(self._game_path, game_archive), 4)
            # Extract just the hash values from the tuples
            hash_values = [h[2] for h in hashes]
            # Use GameDatabase to find game by hashes
            version_id = db.find_game_by_hashes(hash_values)
            if version_id is not None:
                db.add_local_game_version(version_id, game_archive)
            self.progress.emit(index + 1)

        self.load_games.emit()
