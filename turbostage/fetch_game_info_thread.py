import sqlite3

from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage import utils
from turbostage.igdb_client import IgdbClient


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
                utils.epoch_to_formatted_date(release_date),
                genre,
                publisher,
            )
            return

        details = utils.fetch_game_details(self._igdb_client, self._game_id)
        cursor.execute(
            """
            INSERT INTO games (summary, release_date, genre, publisher, cover_url)
            VALUES (?, ?, ?, ?, ?)
            WHERE igdb_id = ?
        """,
            (
                details["summary"],
                details["release_date"],
                details["genres"],
                details["publisher"],
                details["cover"],
                self._game_id,
            ),
        )

        self.finished.emit(
            details["summary"],
            "http:" + details["cover"].replace("t_thumb", "t_cover_big"),
            details["release_date"],
            details["genres"],
            details["publisher"],
        )


class FetchGameInfoTask(QRunnable):
    def __init__(self, worker: FetchGameInfoWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        self._worker.run()
