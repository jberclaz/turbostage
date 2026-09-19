import logging
import os
import shutil
import zipfile

from PySide6.QtCore import QObject, QRunnable, QStandardPaths, Signal

from turbostage import iso_utils, utils
from turbostage.db.game_database import GameDatabase

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    task_finished = Signal()
    task_failed = Signal(str)


class AddGameWorker(QRunnable):
    def __init__(
        self,
        game_name: str,
        version_name: str,
        igdb_id: int,
        game_archive: str,
        binary: str,
        config_binary: str | None,
        cpu_cycles: int,
        config: str,
        db_path: str,
        igdb_client,
        requires_install: bool = False,
        midi_device: int = 0,
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self._game_name = game_name
        self._version_name = version_name
        self._igdb_id = igdb_id
        self._game_archive = game_archive
        self._binary = binary
        self._config_binary = config_binary
        self._cpu_cycles = cpu_cycles
        self._config = config
        self._db_path = db_path
        self._igdb_client = igdb_client
        self._requires_install = requires_install
        self._midi_device = midi_device

    def run(self):
        db = GameDatabase(self._db_path)
        try:
            self._run(db)
        except Exception as e:  # noqa: BLE001 - must always notify UI to avoid stuck BusyCursor
            logger.exception("Failed to add game '%s'", self._game_archive)
            try:
                self.signals.task_failed.emit(str(e))
            except RuntimeError:
                # Signals may be torn down during app shutdown; nothing to notify.
                pass
        finally:
            try:
                db.close()
            except Exception:  # noqa: BLE001 - close must not mask the original result
                pass

    def _run(self, db: GameDatabase):
        from turbostage.db.game_database import GameDetails

        if not self._game_archive or not os.path.isfile(self._game_archive):
            raise FileNotFoundError(f"Game archive not found: '{self._game_archive}'")

        # Determine archive type
        archive_type = iso_utils.get_archive_type(self._game_archive)

        # Strip ISO version number (e.g., ;1) from executables
        binary = self._binary.split(";")[0] if self._binary else None
        config_binary = self._config_binary.split(";")[0] if self._config_binary else None

        # 1. check if game exists in db
        game = db.get_game_details_by_igdb_id(self._igdb_id)
        if game is None:
            # 2.1 query IGDB for extra info (offline-safe: fall back to minimal details)
            details = None
            try:
                details = utils.fetch_game_details_online(self._igdb_client, self._igdb_id)
            except Exception:  # noqa: BLE001 - offline or unknown game must not block adding
                details = None
            if details is None:
                details = GameDetails(
                    title=self._game_name,
                    release_date=None,
                    genre="",
                    summary="",
                    publisher="",
                    developer="",
                    cover_url="",
                    rating=None,
                    igdb_id=self._igdb_id,
                    screenshot_urls="[]",
                )
            # 2.2 add game entry in games table
            db.insert_game_with_details(self._game_name, details)

        # Get the archive basename
        archive_basename = os.path.basename(self._game_archive)

        # 2.5 Check that this version does not already exist
        existing_versions = db.get_all_game_versions(self._igdb_id)
        for existing_version in existing_versions:
            if existing_version.version_name == self._version_name:
                # Version already exists, just update the local version entry
                db.add_local_game_version(
                    existing_version.version_id,
                    archive_basename,
                    archive_type=archive_type,
                    requires_install=self._requires_install,
                )
                self.signals.task_finished.emit()
                return

        # 3. add game version in version table
        version_id = db.insert_game_version(
            self._igdb_id,
            self._version_name,
            binary,
            config_binary,
            self._config,
            self._cpu_cycles,
            requires_install=self._requires_install,
            midi_device=self._midi_device,
        )

        # 4. add hashes based on archive type
        if archive_type == "iso":
            hashes = iso_utils.compute_hash_for_largest_files_in_iso(self._game_archive, n=4)
            # Only compute hash for binary if it's selected (not None/empty)
            if binary and binary not in [h[0] for h in hashes]:
                h = iso_utils.compute_md5_from_iso(self._game_archive, binary)
                hashes.append((binary, 0, h))
        else:
            hashes = utils.compute_hash_for_largest_files_in_zip(self._game_archive, n=4)
            if binary and binary not in [h[0] for h in hashes]:
                with zipfile.ZipFile(self._game_archive, "r") as zf:
                    h = utils.compute_md5_from_zip(zf, binary)
                    hashes.append((binary, 0, h))

        db.insert_multiple_hashes(version_id, hashes)

        # 5. add local version with archive type
        db.add_local_game_version(
            version_id,
            archive_basename,
            archive_type=archive_type,
            requires_install=self._requires_install,
        )

        # 6. For ISO games that require installation, create installation record
        if archive_type == "iso" and self._requires_install:
            app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
            installs_folder = os.path.join(app_data_folder, "installs")
            os.makedirs(installs_folder, exist_ok=True)
            install_path = os.path.join(installs_folder, str(version_id))
            # Clean old install directory if it exists (from a previous deletion)
            if os.path.isdir(install_path):
                shutil.rmtree(install_path)
            os.makedirs(install_path, exist_ok=True)
            db.create_installation(version_id, install_path)

        self.signals.task_finished.emit()
