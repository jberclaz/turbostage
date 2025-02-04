from io import BytesIO

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout


class DownloadWorker(QThread):
    progress_update = Signal(int)
    finished_signal = Signal(bytes)  # Signal emits bytes
    error_signal = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cancelled = False
        self.buffer = BytesIO()  # Initialize buffer

    def run(self):
        try:
            response = requests.get(self.url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            bytes_downloaded = 0

            for chunk in response.iter_content(chunk_size=8192):
                if self.cancelled:
                    return

                self.buffer.write(chunk)  # Write to buffer
                bytes_downloaded += len(chunk)
                progress = int((bytes_downloaded / total_size) * 100) if total_size else 0
                self.progress_update.emit(progress)

            self.finished_signal.emit(self.buffer.getvalue())  # Emit the bytes

        except requests.exceptions.RequestException as e:
            self.error_signal.emit(str(e))
        except Exception as e:
            self.error_signal.emit(str(e))

    def cancel(self):
        self.cancelled = True


class DownloaderDialog(QDialog):
    def __init__(self, parent, title: str = "File Downloader"):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)

        self.layout = QVBoxLayout()

        self.status_label = QLabel("Downloading...")  # Add a status label
        self.layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.layout.addWidget(self.cancel_button)

        self.setLayout(self.layout)

        self.download_worker = None  # Initialize download worker

    def start_download(self, url):
        self.download_worker = DownloadWorker(url)  # No save_path needed

        self.download_worker.progress_update.connect(self.progress_bar.setValue)
        self.download_worker.finished_signal.connect(self.download_finished)
        self.download_worker.error_signal.connect(self.download_error)
        self.download_worker.start()
        self.cancel_button.setEnabled(True)

    def cancel_download(self):
        if self.download_worker:
            self.download_worker.cancel()
            self.status_label.setText("Cancelling download")
            self.cancel_button.setEnabled(False)
            self.download_worker.wait()
        self.reject()

    def download_finished(self, save_path):
        self.accept()

    def download_error(self, error_message):
        self.status_label.setText("Download error.")
        self.progress_bar.setValue(0)  # Reset progress bar if error
