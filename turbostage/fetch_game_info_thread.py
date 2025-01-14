from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage.igdb_client import IgdbClient


class FetchGameInfoWorker(QObject):
    finished = Signal(str, str, str, str, str)

    def __init__(self, game_id: int, igdb_client: IgdbClient, cancel_flag):
        super().__init__()
        self._game_id = game_id
        self._igdb_client = igdb_client
        self._cancel_flag = cancel_flag

    def run(self):
        if self._cancel_flag():
            return

        response = self._igdb_client.query(
            "games",
            ["summary", "storyline", "screenshots", "rating", "release_dates", "involved_companies", "genres", "cover"],
            f"id={self._game_id}",
        )
        if self._cancel_flag():
            return

        assert len(response) == 1
        info = response[0]

        response = self._igdb_client.query("genres", ["name"], f"id=({','.join([str(i) for i in info['genres']])})")
        assert len(response) == len(info["genres"])

        if self._cancel_flag():
            return

        genres_string = ", ".join(r["name"] for r in response)

        dates_result = self._igdb_client.query(
            "release_dates", ["date"], f"platform=13&id=({','.join([str(d) for d in info['release_dates']])})"
        )
        epoch = dates_result[0]["date"]
        dt = datetime.fromtimestamp(epoch)
        formatted_time = dt.strftime("%B %d, %Y")

        if self._cancel_flag():
            return

        response = self._igdb_client.query(
            "involved_companies",
            ["company"],
            f"id=({','.join(str(i) for i in info['involved_companies'])})&developer=true",
        )
        if self._cancel_flag():
            return
        company_ids = set(r["company"] for r in response)
        response = self._igdb_client.query("companies", ["name"], f"id=({','.join(str(i) for i in company_ids)})")
        companies = ", ".join(r["name"] for r in response)
        if self._cancel_flag():
            return

        response = self._igdb_client.query("covers", ["url"], f"id={info['cover']}")
        assert len(response) == 1
        cover_info = response[0]

        self.finished.emit(
            info["summary"],
            "http:" + cover_info["url"].replace("t_thumb", "t_cover_big"),
            formatted_time,
            genres_string,
            companies,
        )


class FetchGameInfoTask(QRunnable):
    def __init__(self, worker: FetchGameInfoWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        self._worker.run()
