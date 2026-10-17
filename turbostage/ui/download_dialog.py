import os
from io import BytesIO

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class DownloadWorker(QThread):
    """Download a URL into memory, or straight to dest_path when given.

    finished_signal carries the BytesIO buffer, or dest_path in file mode.
    """

    progress_update = Signal(int)
    finished_signal = Signal(object)
    error_signal = Signal(str)

    def __init__(self, url, dest_path: str | None = None):
        super().__init__()
        self.url = url
        self.cancelled = False
        self.buffer = BytesIO()
        self._dest_path = dest_path

    def run(self):
        # In file mode, download to a side file and rename it into place only
        # once complete, so a cancelled or failed download never leaves a
        # truncated archive (or clobbers an existing one).
        part_path = self._dest_path + ".part" if self._dest_path else None
        try:
            response = requests.get(self.url, stream=True, headers={"User-Agent": USER_AGENT}, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            bytes_downloaded = 0

            out = open(part_path, "wb") if part_path else self.buffer
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.cancelled:
                        self.buffer = None
                        return

                    out.write(chunk)
                    bytes_downloaded += len(chunk)
                    progress = int((bytes_downloaded / total_size) * 100) if total_size else 0
                    self.progress_update.emit(progress)
            finally:
                if part_path:
                    out.close()

            if part_path:
                os.replace(part_path, self._dest_path)
                part_path = None
                self.finished_signal.emit(self._dest_path)
            else:
                self.buffer.seek(0)
                self.finished_signal.emit(self.buffer)

        except requests.exceptions.RequestException as e:
            self.error_signal.emit(str(e))
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            if part_path and os.path.exists(part_path):
                try:
                    os.unlink(part_path)
                except OSError:
                    pass

    def cancel(self):
        self.cancelled = True


class DownloaderDialog(QDialog):
    def __init__(self, parent, title: str = "File Downloader"):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)

        self.layout = QVBoxLayout()

        self.status_label = QLabel("Downloading...")
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.layout.addWidget(self.cancel_button)

        self.setLayout(self.layout)

        self._download_worker = None
        self.data_buffer = None
        self.downloaded_path = None
        self.error = False

    def start_download(self, url, dest_path: str | None = None):
        """Start downloading url, into data_buffer or (if given) to dest_path."""
        self.error = False
        self._download_worker = DownloadWorker(url, dest_path)

        self._download_worker.progress_update.connect(self.progress_bar.setValue)
        self._download_worker.finished_signal.connect(self.download_finished)
        self._download_worker.error_signal.connect(self.download_error)
        self._download_worker.start()
        self.cancel_button.setEnabled(True)

    def cancel_download(self):
        self.reject()

    def reject(self):
        # Esc and the window close button land here too, not only the Cancel
        # button: never leave a download running behind a closed dialog.
        if self._download_worker is not None and self._download_worker.isRunning():
            self._download_worker.cancel()
            self.status_label.setText("Cancelling download")
            self.cancel_button.setEnabled(False)
            self._download_worker.wait()
        super().reject()

    def download_finished(self, data):
        if isinstance(data, str):
            self.downloaded_path = data
        else:
            self.data_buffer = data
        self.accept()

    def download_error(self, error_message):
        self.error = True
        self.status_label.setText(f"Download failed:\n{error_message}")
        self.progress_bar.setValue(0)
        self.cancel_button.setText("Close")
        self.cancel_button.setEnabled(True)
