import json
import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from turbostage import utils
from turbostage.db.game_database import GameDatabase
from turbostage.igdb_client import IgdbClient

logger = logging.getLogger(__name__)


def _cover_big(url: str | None) -> str:
    """Upgrade an IGDB thumbnail URL to cover-big size (None-safe)."""
    if not url:
        return ""
    return url.replace("t_thumb", "t_cover_big")


def _format_release(release_date) -> str:
    """Format an epoch release date for the finished signal (None-safe)."""
    if release_date is None:
        return ""
    try:
        return utils.epoch_to_formatted_date(int(release_date))
    except (OSError, OverflowError, ValueError, TypeError):
        return ""


class FetchGameInfoWorker(QObject):
    finished = Signal(str, str, str, str, str, str, str, int)

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
        try:
            self._run(db)
        finally:
            try:
                db.close()
            except Exception:  # noqa: BLE001 - close must not mask the fetch result
                pass

    def _run(self, db: GameDatabase):
        game_details = db.get_game_details_by_igdb_id(self._igdb_id)

        if not game_details:
            logger.warning("No database entry for game %s", self._igdb_id)
            return

        if game_details.release_date is not None:
            self.finished.emit(
                game_details.summary or "",
                _cover_big(game_details.cover_url),
                _format_release(game_details.release_date),
                game_details.genre or "",
                game_details.publisher or "",
                game_details.developer or "",
                game_details.screenshot_urls or "[]",
                game_details.rating or 0,
            )
            return

        if self._cancel_flag():
            return

        # If we don't have complete details, fetch them from IGDB
        try:
            details = utils.fetch_game_details_online(self._igdb_client, self._igdb_id)
        except Exception:  # noqa: BLE001 - offline IGDB must not kill the pool thread
            logger.exception("IGDB fetch failed for game %s", self._igdb_id)
            return

        if self._cancel_flag():
            return

        if details is None:
            # Unknown/offline game: show what the DB already has.
            self.finished.emit(
                game_details.summary or "",
                _cover_big(game_details.cover_url),
                "",
                game_details.genre or "",
                game_details.publisher or "",
                game_details.developer or "",
                game_details.screenshot_urls or "[]",
                game_details.rating or 0,
            )
            return

        # Update the database with the fetched details
        try:
            db.update_game_details(self._igdb_id, details)
        except Exception:  # noqa: BLE001 - a failed cache write must not block display
            logger.exception("Failed to cache IGDB details for game %s", self._igdb_id)

        self.finished.emit(
            details.summary or "",
            _cover_big(details.cover_url),
            _format_release(details.release_date),
            details.genre or "",
            details.publisher or "",
            details.developer or "",
            details.screenshot_urls or "[]",
            details.rating or 0,
        )


class FetchGameInfoTask(QRunnable):
    def __init__(self, worker: FetchGameInfoWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        self._worker.run()
