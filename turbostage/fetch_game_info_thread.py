from PySide6.QtCore import QRunnable, Signal, QObject

from turbostage.igdb_client import IgdbClient


class FetchGameInfoWorker(QObject):
    finished = Signal(str)

    def __init__(self, game_id: int, igdb_client: IgdbClient, cancel_flag):
        super().__init__()
        self._game_id = game_id
        self._igdb_client = igdb_client
        self._cancel_flag = cancel_flag

    def run(self):
        if self._cancel_flag():
            return

        info = self._igdb_client.query("games", ["summary", "storyline", "screenshots", "rating", "release_dates",
                                                 "involved_companies", "genres", "cover"], f"id={self._game_id}")

        if self._cancel_flag():
            return

        self.finished.emit(info[0]["cover"])


class FetchGameInfoTask(QRunnable):
    def __init__(self, worker: FetchGameInfoWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        self._worker.run()
