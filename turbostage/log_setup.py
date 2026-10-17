"""Application logging: a rotating log file plus warnings on stderr.

The Windows and macOS builds are windowed, so stderr goes nowhere there: the
log file is the only record of errors for bug reports.
"""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QStandardPaths, QtMsgType, qInstallMessageHandler

from turbostage import __version__

LOG_FILE_NAME = "turbostage.log"
_MAX_BYTES = 1024 * 1024
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"

_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def log_file_path() -> str:
    """Return the log file path, next to the app's database."""
    folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    return os.path.join(folder, LOG_FILE_NAME)


def setup_logging(directory: str | None = None) -> str | None:
    """Log INFO and above to a rotating file, WARNING and above to stderr.

    Also records uncaught exceptions, including those raised in Qt slots and
    worker threads, and Qt's own warnings. Returns the log file path, or None
    if the file cannot be opened (logging then goes to stderr only).
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    if sys.stderr is not None:  # None in windowed PyInstaller builds on Windows
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(formatter)
        root.addHandler(console)

    log_path = None
    try:
        log_path = os.path.join(directory, LOG_FILE_NAME) if directory else log_file_path()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_handler = RotatingFileHandler(log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
    except OSError as e:
        root.warning("Cannot open log file %s: %s", log_path, e)
        log_path = None
    else:
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _install_exception_hooks()
    qInstallMessageHandler(_qt_message_handler)
    logging.getLogger(__name__).info("TurboStage %s starting on %s", __version__, sys.platform)
    return log_path


def _install_exception_hooks():
    previous_hook = sys.excepthook

    def excepthook(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logging.getLogger("turbostage").critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        previous_hook(exc_type, exc_value, exc_tb)

    def thread_excepthook(args):
        logging.getLogger("turbostage").critical(
            "Uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


def _qt_message_handler(msg_type, context, message):
    logging.getLogger("qt").log(_QT_LEVELS.get(msg_type, logging.WARNING), message)
