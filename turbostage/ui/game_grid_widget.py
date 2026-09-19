import hashlib
import logging
import os

from PySide6.QtCore import QSize, QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from turbostage import utils
from turbostage.db.game_database import LocalGameDetails
from turbostage.ui.theme import muted_text_color

logger = logging.getLogger(__name__)

COVER_WIDTH = 120
COVER_HEIGHT = 160
DOWNLOADABLE_OPACITY = 0.45

BADGE_DOWNLOAD = "Download"
BADGE_INSTALL = "Install"


def badge_for_item(needs_install: bool, is_downloadable: bool) -> str | None:
    """Return the badge text for a game, or None when it is ready to play."""
    if is_downloadable:
        return BADGE_DOWNLOAD
    if needs_install:
        return BADGE_INSTALL
    return None


class GameGridWidget(QListWidget):
    """Grid of game cover images with the game title underneath."""

    def __init__(self, parent=None):
        super().__init__(parent)

        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self._covers_cache_folder = os.path.join(app_data_folder, "image_cache", "covers")
        os.makedirs(self._covers_cache_folder, exist_ok=True)
        utils.prune_image_cache(self._covers_cache_folder)

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
            title = game.title or "Unknown"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, (game.igdb_id, game.version_id, needs_install, is_downloadable))
            item.setSizeHint(self.gridSize())
            if is_downloadable:
                item.setForeground(QColor(150, 150, 150))
                item.setToolTip(f"{title} — click to download")
            elif needs_install:
                item.setToolTip(f"{title} — needs installation")
            else:
                item.setToolTip(title)
            self.addItem(item)

            if game.cover_url:
                self._load_cover(game.version_id, game.cover_url)
            else:
                self._set_item_icon(item, QPixmap(), title=title)

    def _load_cover(self, version_id: int, url: str) -> None:
        file_name = f"{hashlib.md5(url.encode()).hexdigest()}.jpg"
        local_path = os.path.join(self._covers_cache_folder, file_name)

        if os.path.exists(local_path):
            item = self._find_item(version_id)
            if item is not None:
                self._set_item_icon(item, QPixmap(local_path))
        else:
            request = QNetworkRequest(QUrl(url))
            # Store the version key (not the QListWidgetItem pointer): the
            # item may be deleted by clear()/set_games() before the reply
            # arrives, which would leave a dangling C++ pointer.
            request.setAttribute(QNetworkRequest.Attribute.User, (local_path, version_id))
            self.network_manager.get(request)

    def _find_item(self, version_id: int) -> QListWidgetItem | None:
        for index in range(self.count()):
            item = self.item(index)
            try:
                data = item.data(Qt.UserRole)
            except RuntimeError:
                continue
            if data and len(data) >= 2 and data[1] == version_id:
                return item
        return None

    def _set_item_icon(self, item: QListWidgetItem, pixmap: QPixmap, title: str = "") -> None:
        if pixmap.isNull():
            pixmap = self._make_placeholder(title or item.text())
        else:
            pixmap = pixmap.scaled(
                QSize(COVER_WIDTH, COVER_HEIGHT),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if self._is_downloadable(item):
            pixmap = self._fade_pixmap(pixmap, DOWNLOADABLE_OPACITY)
        badge = self._badge_for_item(item)
        if badge:
            pixmap = self._add_badge(pixmap, badge)
        item.setIcon(QIcon(pixmap))

    @staticmethod
    def _make_placeholder(title: str) -> QPixmap:
        """A cover placeholder showing the game's initial instead of a blank box."""
        pixmap = QPixmap(COVER_WIDTH, COVER_HEIGHT)
        pixmap.fill(QColor("#3a3f4a"))
        painter = QPainter(pixmap)
        painter.setPen(QColor(muted_text_color()))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(56)
        painter.setFont(font)
        initial = title.strip()[:1].upper() or "?"
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initial)
        painter.end()
        return pixmap

    @staticmethod
    def _badge_for_item(item: QListWidgetItem) -> str | None:
        data = item.data(Qt.UserRole)
        if not data or len(data) < 4:
            return None
        _, _, needs_install, is_downloadable = data[:4]
        return badge_for_item(bool(needs_install), bool(is_downloadable))

    @staticmethod
    def _add_badge(pixmap: QPixmap, text: str) -> QPixmap:
        """Paint a small status pill at the bottom-left of a cover."""
        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(11)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        padding_x, padding_y = 7, 4
        text_width = metrics.horizontalAdvance(text)
        text_height = metrics.height()
        badge_width = text_width + 2 * padding_x
        badge_height = text_height + 2 * padding_y
        x, y = 6, pixmap.height() - badge_height - 6
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 30, 210))
        painter.drawRoundedRect(x, y, badge_width, badge_height, 8, 8)
        painter.setPen(QColor("#ffd75e"))
        painter.drawText(x, y, badge_width, badge_height, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return result

    @staticmethod
    def _is_downloadable(item: QListWidgetItem) -> bool:
        data = item.data(Qt.UserRole)
        return bool(data) and len(data) >= 4 and data[3]

    @staticmethod
    def _fade_pixmap(pixmap: QPixmap, opacity: float) -> QPixmap:
        faded = QPixmap(pixmap.size())
        faded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(faded)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return faded

    @Slot(QNetworkReply)
    def _on_image_download_finished(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                logger.warning("Cover download failed: %s", reply.errorString())
                return

            try:
                local_path, version_id = reply.request().attribute(QNetworkRequest.Attribute.User)
            except (TypeError, ValueError):
                logger.warning("Cover reply missing request metadata; ignoring")
                return
            if not local_path or version_id is None:
                return

            image_data = reply.readAll()
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_data) or pixmap.isNull():
                logger.warning("Downloaded cover is not a valid image; ignoring")
                return
            try:
                pixmap.save(local_path, "JPG", 90)
            except OSError:
                logger.exception("Failed to cache cover '%s'", local_path)
            item = self._find_item(version_id)
            if item is None:
                # Library was cleared/reloaded while downloading; the file is
                # cached for next time, there is just nothing to paint now.
                return
            try:
                self._set_item_icon(item, pixmap)
            except RuntimeError:
                # Item was deleted between lookup and painting; ignore.
                pass
        finally:
            reply.deleteLater()
