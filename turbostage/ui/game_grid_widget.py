import hashlib
import os

from PySide6.QtCore import QSize, QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from turbostage.db.game_database import LocalGameDetails

COVER_WIDTH = 120
COVER_HEIGHT = 160


class GameGridWidget(QListWidget):
    """Grid of game cover images with the game title underneath."""

    def __init__(self, parent=None):
        super().__init__(parent)

        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self._covers_cache_folder = os.path.join(app_data_folder, "image_cache", "covers")
        os.makedirs(self._covers_cache_folder, exist_ok=True)

        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self._on_image_download_finished)

        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(COVER_WIDTH, COVER_HEIGHT))
        self.setGridSize(QSize(COVER_WIDTH + 20, COVER_HEIGHT + 44))
        self.setSpacing(8)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideRight)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def set_games(self, entries: list[tuple[LocalGameDetails, bool, bool]]) -> None:
        """Populate the grid.

        Args:
            entries: List of (game, needs_install, is_downloadable) tuples.
        """
        self.clear()
        for game, needs_install, is_downloadable in entries:
            item = QListWidgetItem(game.title)
            item.setData(Qt.UserRole, (game.igdb_id, game.version_id, needs_install, is_downloadable))
            item.setToolTip(game.title)
            item.setSizeHint(self.gridSize())
            self.addItem(item)

            if game.cover_url:
                self._load_cover(item, game.cover_url)
            else:
                item.setIcon(self._placeholder_icon())

    def _load_cover(self, item: QListWidgetItem, url: str) -> None:
        file_name = f"{hashlib.md5(url.encode()).hexdigest()}.jpg"
        local_path = os.path.join(self._covers_cache_folder, file_name)

        if os.path.exists(local_path):
            self._set_item_icon(item, QPixmap(local_path))
        else:
            request = QNetworkRequest(QUrl(url))
            request.setAttribute(QNetworkRequest.Attribute.User, (local_path, item))
            self.network_manager.get(request)

    def _set_item_icon(self, item: QListWidgetItem, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            item.setIcon(self._placeholder_icon())
            return
        scaled = pixmap.scaled(
            QSize(COVER_WIDTH, COVER_HEIGHT),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        item.setIcon(QIcon(scaled))

    @staticmethod
    def _placeholder_icon() -> QIcon:
        pixmap = QPixmap(COVER_WIDTH, COVER_HEIGHT)
        pixmap.fill(QColor("#2c2c2c"))
        return QIcon(pixmap)

    @Slot(QNetworkReply)
    def _on_image_download_finished(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return

        local_path, item = reply.request().attribute(QNetworkRequest.Attribute.User)
        image_data = reply.readAll()
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        pixmap.save(local_path, "JPG", 90)
        self._set_item_icon(item, pixmap)
        reply.deleteLater()
