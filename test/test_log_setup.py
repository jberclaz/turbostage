import logging
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from turbostage import log_setup


class TestSetupLogging(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        saved = (root.level, list(root.handlers), sys.excepthook, threading.excepthook)

        def restore():
            for handler in root.handlers:
                if handler not in saved[1]:
                    handler.close()
            root.setLevel(saved[0])
            root.handlers[:] = saved[1]
            sys.excepthook, threading.excepthook = saved[2], saved[3]
            log_setup.qInstallMessageHandler(None)

        self.addCleanup(restore)
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.dir = tempdir.name

    def _read_log(self, path):
        for handler in logging.getLogger().handlers:
            handler.flush()
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_info_goes_to_log_file(self):
        path = log_setup.setup_logging(self.dir)
        logging.getLogger("turbostage.something").info("hello from a module")
        log = self._read_log(path)
        self.assertIn("starting on", log)
        self.assertIn("hello from a module", log)

    def test_uncaught_exception_is_logged(self):
        path = log_setup.setup_logging(self.dir)
        try:
            raise ValueError("boom in a slot")
        except ValueError:
            with patch("sys.__excepthook__"), patch("sys.stderr"):
                sys.excepthook(*sys.exc_info())
        log = self._read_log(path)
        self.assertIn("Uncaught exception", log)
        self.assertIn("ValueError: boom in a slot", log)

    def test_uncaught_thread_exception_is_logged(self):
        path = log_setup.setup_logging(self.dir)
        thread = threading.Thread(target=lambda: 1 / 0, name="worker-1")
        thread.start()
        thread.join()
        log = self._read_log(path)
        self.assertIn("Uncaught exception in thread worker-1", log)
        self.assertIn("ZeroDivisionError", log)

    def test_windowed_build_without_stderr(self):
        with patch("sys.stderr", None):
            path = log_setup.setup_logging(self.dir)
            logging.getLogger("turbostage").warning("no console here")
        self.assertIn("no console here", self._read_log(path))

    def test_unwritable_log_folder_falls_back_to_stderr(self):
        self.assertIsNone(log_setup.setup_logging("/nonexistent/turbostage/logs"))


if __name__ == "__main__":
    unittest.main()
