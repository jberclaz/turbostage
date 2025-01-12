from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import QNetworkRequest, QNetworkAccessManager, QNetworkReply
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QUrl, Slot


class GameInfoWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout(self)

        self.game_info_label = QLabel("Select a game to see details here.")
        self.game_info_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.layout.addWidget(self.game_info_label)

        self.cover_image = QLabel()
        self.cover_image.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.layout.addWidget(self.cover_image)

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignTop)
        self.layout.addWidget(self.summary)

        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_image_download_finished)

    def set_game_name(self, game_name: str):
        self.game_info_label.setText(f"<b>{game_name}</b>")

    def set_game_info(self, summary: str, cover_url: str):
        self.summary.setText(summary)
        request = QNetworkRequest(QUrl(cover_url))
        self.network_manager.get(request)

    @Slot(QNetworkReply)
    def on_image_download_finished(self, reply):
        image_data = reply.readAll()
        image = QImage()
        image.loadFromData(image_data)
        pixmap = QPixmap(image)
        self.cover_image.setPixmap(pixmap.scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio))
