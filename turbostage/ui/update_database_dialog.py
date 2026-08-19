import gzip
import json

import requests
from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from turbostage.db.game_database import GameDatabase

SPINNER_COLOR = "#3a6ea5"


class SpinnerWidget(QWidget):
    """A small animated circular spinner drawn without any image assets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(28, 28)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(50)

    def _rotate(self):
        self._angle = (self._angle + 15) % 360
        self.update()

    def stop(self):
        self._timer.stop()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(SPINNER_COLOR))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.drawArc(rect, -self._angle * 16, 120 * 16)
        painter.end()


class UpdateDatabaseWorker(QThread):
    success = Signal(str)
    error = Signal(str)

    def __init__(self, db_path: str, online_db_url: str, igdb_client):
        super().__init__()
        self._db_path = db_path
        self._online_db_url = online_db_url
        self._igdb_client = igdb_client

    def run(self):
        try:
            response = requests.get(self._online_db_url, timeout=60)
            if response.status_code != 200:
                self.error.emit(f"Unable to access online database (HTTP {response.status_code}).")
                return

            data = gzip.decompress(response.content)
            database = json.loads(data.decode("utf-8"))

            db = GameDatabase(self._db_path)
            result = db.merge_remote_json(database, self._igdb_client)
            self.success.emit(result)
        except requests.exceptions.RequestException as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))


class UpdateDatabaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Game Database")
        self.setModal(True)
        self.setMinimumWidth(380)

        self._finished = False

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self._spinner = SpinnerWidget()
        row.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignTop)
        self.status_label = QLabel("Updating game database...")
        self.status_label.setWordWrap(True)
        row.addWidget(self.status_label, 1)
        layout.addLayout(row)

        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

    def show_success(self, message: str):
        self._finished = True
        self._spinner.stop()
        self.status_label.setText(f"Game database updated successfully.\n{message}")
        self.close_button.setEnabled(True)

    def show_error(self, message: str):
        self._finished = True
        self._spinner.stop()
        self.status_label.setText(f"Unable to update the game database:\n{message}")
        self.close_button.setEnabled(True)

    def reject(self):
        if self._finished:
            super().reject()

    def closeEvent(self, event):
        if self._finished:
            super().closeEvent(event)
        else:
            event.ignore()
