"""Where TurboStage keeps its own files (library database, logs, caches, downloads).

Everything lives in a "TurboStage" folder inside the platform's data folder:
~/.local/share/TurboStage on Linux, ~/Library/Application Support/TurboStage
on macOS, %APPDATA%\\TurboStage on Windows (inside a Flatpak, the sandbox's
own data folder). Versions up to 0.13 put these files directly in the data
folder itself; turbostage.data_migration moves them.
"""

import os

from PySide6.QtCore import QStandardPaths

APP_FOLDER_NAME = "TurboStage"

# Set when this session has to keep using the old location (see use_legacy_root).
_override: str | None = None


def platform_data_root() -> str:
    """The platform's per-user data folder, e.g. ~/.local/share.

    QStandardPaths' AppDataLocation ends with the application name, which
    depends on how Python was started, so its parent is used instead.
    """
    return os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))


def data_dir() -> str:
    """TurboStage's own data folder (created if needed)."""
    path = _override or os.path.join(platform_data_root(), APP_FOLDER_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def data_path(*parts: str) -> str:
    """A path inside the data folder."""
    return os.path.join(data_dir(), *parts)


def data_subdir(name: str) -> str:
    """A subfolder of the data folder (created if needed)."""
    path = data_path(name)
    os.makedirs(path, exist_ok=True)
    return path


def use_legacy_root() -> None:
    """Keep using the old location (the data root itself) for this session.

    Used when the library database could not be moved, so the app never
    starts with an empty library next to the real one.
    """
    global _override
    _override = platform_data_root()


def reset() -> None:
    """Forget a legacy-root override (tests)."""
    global _override
    _override = None
