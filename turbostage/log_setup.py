"""Application logging: a rotating log file plus warnings on stderr.

The Windows and macOS builds are windowed, so stderr goes nowhere there: the
log file is the only record of errors for bug reports.
"""

import faulthandler
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

from turbostage import __version__, app_paths

LOG_FILE_NAME = "turbostage.log"
DOSBOX_LOG_FILE_NAME = "dosbox.log"
# Stack traces of native crashes (segfaults in Qt, ...), which logging cannot record.
CRASH_FILE_NAME = "crash.log"
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
    return app_paths.data_path(LOG_FILE_NAME)


def dosbox_log_file_path() -> str:
    """Return the path of the DOSBox output of the last game run, next to the log file."""
    return os.path.join(os.path.dirname(log_file_path()), DOSBOX_LOG_FILE_NAME)


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
    if log_path:
        _enable_crash_traces(os.path.join(os.path.dirname(log_path), CRASH_FILE_NAME))
    return log_path


_crash_file = None  # kept open for faulthandler


def _enable_crash_traces(path: str) -> None:
    """Record native crashes in crash.log; report the previous session's into the log.

    A crash inside Qt or another C library kills the process before Python
    can log anything. faulthandler writes the Python stack of every thread to
    a file instead; the next start copies it into the log, which is what
    users send with bug reports.
    """
    global _crash_file
    log = logging.getLogger(__name__)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            previous = f.read().strip()
    except OSError:
        previous = ""
    if previous:
        log.error("The previous session crashed:\n%s", previous)
    try:
        if _crash_file is not None:
            _crash_file.close()
        _crash_file = open(path, "w", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    except OSError as e:
        log.warning("Cannot record crash traces in %s: %s", path, e)


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
