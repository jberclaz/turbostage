from PySide6.QtCore import QRunnable, Signal, QObject

from turbostage.igdb_client import IgdbClient


class FetchGameInfoWorker(QObject):
    finished = Signal(str, str)

    def __init__(self, game_id: int, igdb_client: IgdbClient, cancel_flag):
        super().__init__()
        self._game_id = game_id
        self._igdb_client = igdb_client
        self._cancel_flag = cancel_flag

    def run(self):
        if self._cancel_flag():
            return

        response = self._igdb_client.query("games", ["summary", "storyline", "screenshots", "rating", "release_dates",
                                                 "involved_companies", "genres", "cover"], f"id={self._game_id}")
        if self._cancel_flag():
            return

        assert len(response) == 1
        info = response[0]

        response = self._igdb_client.query("covers", ["url"], f"id={info['cover']}")
        assert len(response) == 1
        cover_info = response[0]

        self.finished.emit(info["summary"], "http:" + cover_info["url"].replace("t_thumb", "t_cover_big"))


class FetchGameInfoTask(QRunnable):
    def __init__(self, worker: FetchGameInfoWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        self._worker.run()
