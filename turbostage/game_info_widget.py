import hashlib
import os

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class GameInfoWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout(self)

        self.game_info_label = QLabel("Select a game to see details here.")
        self.game_info_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.layout.addWidget(self.game_info_label)

        self.details_label = QLabel()
        self.details_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.layout.addWidget(self.details_label)

        self.info_layout = QHBoxLayout()

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.info_layout.addWidget(self.summary)

        self.cover_image = QLabel()
        self.info_layout.addWidget(self.cover_image)
        self.layout.addLayout(self.info_layout)

        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_image_download_finished)

        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self._covers_cache_folder = os.path.join(app_data_folder, "covers")
        if not os.path.isdir(self._covers_cache_folder):
            os.makedirs(self._covers_cache_folder)

    def set_game_name(self, game_name: str):
        self.game_info_label.setText(f"<h2>{game_name}</h2>")

    def set_game_info(
        self, summary: str, cover_url: str, release_date: str = None, genres: str = None, publisher: str = None
    ):
        html_content = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="font-weight: bold; text-align: left; padding: 5px;">Release Date:</td>
                    <td style="text-align: left; padding: 5px;">{release_date}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; text-align: left; padding: 5px;">Genre:</td>
                    <td style="text-align: left; padding: 5px;">{genres}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; text-align: left; padding: 5px;">Publisher:</td>
                    <td style="text-align: left; padding: 5px;">{publisher}</td>
                </tr>
            </table>
        </div>
        """
        self.details_label.setText(html_content)
        self.summary.setText(summary)

        local_cover_url = self._local_cover_cache_url
        if os.path.isfile(local_cover_url):
            pixmap = QPixmap(local_cover_url)
            self.cover_image.setPixmap(pixmap.scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            request = QNetworkRequest(QUrl(cover_url))
            self.network_manager.get(request)

    @Slot(QNetworkReply)
    def on_image_download_finished(self, reply):
        image_data = reply.readAll()
        with open(self._local_cover_cache_url, "wb") as image_file:
            image_file.write(image_data)
        image = QImage()
        image.loadFromData(image_data)
        pixmap = QPixmap(image)
        self.cover_image.setPixmap(pixmap.scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio))

    @property
    def _local_cover_cache_url(self):
        image_name = f"{hashlib.md5(self.game_info_label.text().encode()).hexdigest()}.jpg"
        return os.path.join(self._covers_cache_folder, image_name)
