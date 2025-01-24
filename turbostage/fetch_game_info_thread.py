import sqlite3
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage.igdb_client import IgdbClient
from turbostage.utils import epoch_to_formatted_date


class FetchGameInfoWorker(QObject):
    finished = Signal(str, str, str, str, str)

    def __init__(self, game_id: int, igdb_client: IgdbClient, db_path: str, cancel_flag):
        super().__init__()
        self._game_id = game_id
        self._igdb_client = igdb_client
        self._cancel_flag = cancel_flag
        self._db_path = db_path

    def run(self):
        if self._cancel_flag():
            return

        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT release_date, genre, summary, publisher, cover_url
            FROM games
            WHERE igdb_id = ?
            """,
            (self._game_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        if len(rows) != 1:
            raise RuntimeError(f"No database entry for game {self._game_id}")
        row = rows[0]
        release_date = row[0]
        if release_date is not None:
            genre = row[1]
            summary = row[2]
            publisher = row[3]
            self.finished.emit(
                summary,
                "http:" + row[4].replace("t_thumb", "t_cover_big"),
                epoch_to_formatted_date(release_date),
                genre,
                publisher,
            )

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
        formatted_time = epoch_to_formatted_date(dates_result[0]["date"])

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
