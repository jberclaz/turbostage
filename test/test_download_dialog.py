import os
import tempfile
import threading
from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests
from PySide6.QtWidgets import QApplication

from turbostage.ui.download_dialog import DownloaderDialog, DownloadWorker


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def _response(chunks):
    response = MagicMock()
    response.headers = {"content-length": str(sum(len(c) for c in chunks))}
    response.iter_content.return_value = iter(chunks)
    return response


class TestDownloadWorkerToFile(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = os.path.join(self.tmp.name, "game.zip")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, worker):
        seen = {"finished": [], "errors": []}
        worker.finished_signal.connect(lambda v: seen["finished"].append(v))
        worker.error_signal.connect(lambda m: seen["errors"].append(m))
        worker.run()
        return seen

    def test_writes_file_and_reports_path(self):
        worker = DownloadWorker("https://x/game.zip", self.dest)
        with patch("turbostage.ui.download_dialog.requests.get", return_value=_response([b"abc", b"def"])):
            seen = self._run(worker)
        self.assertEqual(seen["finished"], [self.dest])
        with open(self.dest, "rb") as f:
            self.assertEqual(f.read(), b"abcdef")
        self.assertEqual(os.listdir(self.tmp.name), ["game.zip"])

    def test_cancel_leaves_existing_file_untouched(self):
        with open(self.dest, "wb") as f:
            f.write(b"old")
        worker = DownloadWorker("https://x/game.zip", self.dest)

        def chunks():
            yield b"new"
            worker.cancel()
            yield b"more"

        response = _response([])
        response.iter_content.return_value = chunks()
        with patch("turbostage.ui.download_dialog.requests.get", return_value=response):
            seen = self._run(worker)
        self.assertEqual(seen["finished"], [])
        with open(self.dest, "rb") as f:
            self.assertEqual(f.read(), b"old")
        self.assertEqual(os.listdir(self.tmp.name), ["game.zip"])

    def test_network_error_removes_partial_file(self):
        def chunks():
            yield b"partial"
            raise requests.exceptions.ConnectionError("reset")

        response = _response([])
        response.iter_content.return_value = chunks()
        worker = DownloadWorker("https://x/game.zip", self.dest)
        with patch("turbostage.ui.download_dialog.requests.get", return_value=response):
            seen = self._run(worker)
        self.assertEqual(len(seen["errors"]), 1)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_memory_mode_still_returns_buffer(self):
        worker = DownloadWorker("https://x/roms.zip")
        with patch("turbostage.ui.download_dialog.requests.get", return_value=_response([b"rom"])):
            seen = self._run(worker)
        self.assertEqual(seen["finished"][0].getvalue(), b"rom")


class TestDownloaderDialogReject(TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_escape_cancels_running_download(self):
        started = threading.Event()
        release = threading.Event()

        def chunks():
            while not release.is_set():
                started.set()
                yield b"x"

        response = _response([])
        response.iter_content.return_value = chunks()
        dialog = DownloaderDialog(None)
        try:
            with patch("turbostage.ui.download_dialog.requests.get", return_value=response):
                dialog.start_download("https://x/game.zip")
                self.assertTrue(started.wait(5))
                dialog.reject()  # what Esc / the window close button call
            worker = dialog._download_worker
            self.assertTrue(worker.cancelled)
            self.assertFalse(worker.isRunning())
        finally:
            release.set()
            dialog.deleteLater()
