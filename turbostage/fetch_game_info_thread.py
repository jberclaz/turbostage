from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage import utils
from turbostage.db.game_database import GameDatabase
from turbostage.igdb_client import IgdbClient


class FetchGameInfoWorker(QObject):
    finished = Signal(str, str, str, str, str)

    def __init__(self, game_id: int, igdb_client: IgdbClient, db_path: str, cancel_flag):
        super().__init__()
        self._igdb_id = game_id
        self._igdb_client = igdb_client
        self._cancel_flag = cancel_flag
        self._db_path = db_path

    def run(self):
        if self._cancel_flag():
            return

        db = GameDatabase(self._db_path)
        game_details = db.get_game_details_by_igdb_id(self._igdb_id)

        if not game_details:
            raise RuntimeError(f"No database entry for game {self._igdb_id}")

        if game_details.release_date is not None:
            self.finished.emit(
                game_details.summary,
                game_details.cover_url.replace("t_thumb", "t_cover_big"),
                utils.epoch_to_formatted_date(game_details.release_date),
                game_details.genre,
                game_details.publisher,
            )
            return

        # If we don't have complete details, fetch them from IGDB
        details = utils.fetch_game_details_online(self._igdb_client, self._igdb_id)

        # Update the database with the fetched details
        db.update_game_details(self._igdb_id, details)

        self.finished.emit(
            details.summary,
            "http:" + details.cover_url.replace("t_thumb", "t_cover_big"),
            details.release_date,
            details.genre,
            details.publisher,
        )


class FetchGameInfoTask(QRunnable):
    def __init__(self, worker: FetchGameInfoWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        self._worker.run()
