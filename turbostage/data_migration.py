"""Move files of TurboStage <= 0.13 from the shared data folder into its own folder.

Older versions wrote their library database, logs, caches and downloads
directly into the platform data folder (e.g. ~/.local/share/turbostage.db),
next to other applications' files. This runs once at startup, before
anything opens them, and moves them into app_paths.data_dir():

- the library database (SQLite in WAL mode: checkpointed, then moved with
  its side files), the logs, and the cover/screenshot cache;
- the DOSBox, MT-32 ROM and Sound Canvas ROM folders, only when the settings
  point into them (such generic folder names may belong to other programs);
  the settings are rewritten;
- the CD-ROM installations folder, when the library references it or it
  only holds TurboStage's numbered folders; the library paths are rewritten.

Moves are renames within the same parent folder: nothing is copied or
deleted, and nothing already in the new folder is overwritten. If the
database cannot be moved, the session keeps using the old location.
"""

import logging
import os
import sqlite3
from dataclasses import dataclass, field

from turbostage import app_paths

logger = logging.getLogger(__name__)

DB_NAME = "turbostage.db"
DB_SIDE_FILES = ("-wal", "-shm", "-journal")
LOG_NAMES = ("turbostage.log", "turbostage.log.1", "turbostage.log.2", "turbostage.log.3", "dosbox.log")
CACHE_NAME = "image_cache"
INSTALLS_NAME = "installs"
# (setting holding a path inside the folder, folder name)
SETTING_FOLDERS = (
    ("app/emulator_path", "dosbox"),
    ("app/mt32_path", "mt32_roms"),
    ("app/soundcanvas_path", "soundcanvas_roms"),
)


@dataclass
class MigrationResult:
    use_new_folder: bool = True
    moved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def log(self) -> None:
        """Report what happened (call once logging is set up)."""
        if self.moved:
            logger.info("Moved to TurboStage's data folder: %s", ", ".join(self.moved))
        for warning in self.warnings:
            logger.warning(warning)


def _inside(path: str, folder: str) -> bool:
    path, folder = (os.path.normcase(os.path.abspath(p)) for p in (path, folder))
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # different drives on Windows
        return False


def _rebase(path: str, old_folder: str, new_folder: str) -> str:
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(old_folder))
    return new_folder if rel == os.curdir else os.path.join(new_folder, rel)


class _Mover:
    def __init__(self, root: str, target: str, result: MigrationResult):
        self.root, self.target, self.result = root, target, result

    def move(self, name: str) -> bool:
        src, dst = os.path.join(self.root, name), os.path.join(self.target, name)
        if not os.path.lexists(src):
            return False
        if os.path.lexists(dst):
            self.result.warnings.append(f"Not moving '{src}': '{dst}' already exists")
            return False
        try:
            os.rename(src, dst)
        except OSError as e:
            self.result.warnings.append(f"Could not move '{src}' to '{dst}': {e}")
            return False
        self.result.moved.append(name)
        return True


def _checkpoint(db_file: str) -> None:
    """Write the WAL side file back into the main database file."""
    conn = sqlite3.connect(db_file, timeout=5)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _installation_paths(db_file: str) -> list[tuple[int, str]]:
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute("SELECT version_id, install_path FROM installations").fetchall()
    except sqlite3.Error:  # an old schema without the table
        return []
    finally:
        conn.close()


def _rewrite_installation_paths(db_file: str, old_folder: str, new_folder: str) -> int:
    conn = sqlite3.connect(db_file)
    try:
        rows = conn.execute("SELECT version_id, install_path FROM installations").fetchall()
        changed = 0
        for version_id, path in rows:
            if path and _inside(path, old_folder):
                conn.execute(
                    "UPDATE installations SET install_path = ? WHERE version_id = ?",
                    (_rebase(path, old_folder, new_folder), version_id),
                )
                changed += 1
        conn.commit()
        return changed
    finally:
        conn.close()


def migrate_legacy_data(settings, root: str | None = None, target: str | None = None) -> MigrationResult:
    """Move old-location files into the data folder. Never raises."""
    result = MigrationResult()
    root = root or app_paths.platform_data_root()
    target = target or os.path.join(root, app_paths.APP_FOLDER_NAME)
    try:
        _migrate(settings, root, target, result)
    except Exception as e:  # noqa: BLE001 - startup must go on; keep the old location to be safe
        result.warnings.append(f"Moving files to TurboStage's data folder failed: {e}")
        if os.path.exists(os.path.join(root, DB_NAME)):
            result.use_new_folder = False
    return result


def _migrate(settings, root: str, target: str, result: MigrationResult) -> None:
    legacy_db = os.path.join(root, DB_NAME)
    mover = _Mover(root, target, result)
    os.makedirs(target, exist_ok=True)

    # 1. The library database, all or nothing.
    if os.path.exists(legacy_db):
        if os.path.exists(os.path.join(target, DB_NAME)):
            result.warnings.append(
                f"Both '{legacy_db}' and '{os.path.join(target, DB_NAME)}' exist; using the latter, "
                "the old one is left untouched"
            )
        else:
            try:
                _checkpoint(legacy_db)
            except sqlite3.Error as e:
                result.warnings.append(f"Could not prepare '{legacy_db}' for moving: {e}")
                result.use_new_folder = False
                return
            if not mover.move(DB_NAME):
                result.use_new_folder = False
                return
            for suffix in DB_SIDE_FILES:
                mover.move(DB_NAME + suffix)

    # 2. Logs and the cover/screenshot cache.
    for name in LOG_NAMES:
        mover.move(name)
    cache = os.path.join(root, CACHE_NAME)
    if any(os.path.isdir(os.path.join(cache, sub)) for sub in ("covers", "screenshots")):
        mover.move(CACHE_NAME)

    # 3. Downloads, when the settings show they are TurboStage's.
    for key, name in SETTING_FOLDERS:
        old_folder = os.path.join(root, name)
        value = str(settings.value(key, "") or "")
        if value and os.path.isdir(old_folder) and _inside(value, old_folder) and mover.move(name):
            settings.setValue(key, _rebase(value, old_folder, os.path.join(target, name)))

    # 4. CD-ROM installations, with their paths in the library.
    old_installs = os.path.join(root, INSTALLS_NAME)
    db_file = os.path.join(target, DB_NAME)
    if os.path.isdir(old_installs):
        referenced = (
            any(path and _inside(path, old_installs) for _, path in _installation_paths(db_file))
            if os.path.exists(db_file)
            else False
        )
        numbered_only = all(child.isdigit() for child in os.listdir(old_installs))
        if (referenced or numbered_only) and mover.move(INSTALLS_NAME) and os.path.exists(db_file):
            _rewrite_installation_paths(db_file, old_installs, os.path.join(target, INSTALLS_NAME))

    settings.sync()
