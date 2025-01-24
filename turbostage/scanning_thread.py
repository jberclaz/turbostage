import os
import sqlite3

from PySide6.QtCore import QThread, Signal

from turbostage import utils


class ScanningThread(QThread):
    progress = Signal(int)
    load_games = Signal()

    def __init__(self, local_game_archives: list[str], db_path: str, games_path: str):
        super().__init__()
        self._local_game_archives = local_game_archives
        self._db_path = db_path
        self._game_path = games_path

    def run(self):
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM local_versions")

        for index, game_archive in enumerate(self._local_game_archives):
            hashes = utils.compute_hash_for_largest_files_in_zip(os.path.join(self._game_path, game_archive), 4)
            version_id = utils.find_game_for_hashes([h[2] for h in hashes], self._db_path)
            if version_id is not None:
                cursor.execute(
                    "INSERT INTO local_versions (version_id, archive) VALUES (?, ?)", (version_id, game_archive)
                )
            self.progress.emit(index + 1)

        conn.commit()
        conn.close()

        self.load_games.emit()
