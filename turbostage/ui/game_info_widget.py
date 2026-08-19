import hashlib
import json
import os

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from turbostage.ui.theme import border_color, group_box_style, muted_text_color

COVER_WIDTH = 180
COVER_HEIGHT = 240


class GameInfoWidget(QWidget):
    def __init__(self):
        super().__init__()

        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self._cache_folder = os.path.join(app_data_folder, "image_cache")
        self._covers_cache_folder = os.path.join(self._cache_folder, "covers")
        self._screenshots_cache_folder = os.path.join(self._cache_folder, "screenshots")
        os.makedirs(self._covers_cache_folder, exist_ok=True)
        os.makedirs(self._screenshots_cache_folder, exist_ok=True)

        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_image_download_finished)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(14)

        # Title
        self.title_label = QLabel("Select a game to see details here.")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold;")

        # Details group (cover + fields)
        self.details_group = self._make_group("Details")
        details_layout = QHBoxLayout(self.details_group)
        details_layout.setSpacing(16)
        self.cover_image_label = QLabel()
        self.cover_image_label.setFixedSize(COVER_WIDTH, COVER_HEIGHT)
        self.cover_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_image_label.setStyleSheet(
            f"background-color: #2c2c2c; border: 1px solid {border_color()}; border-radius: 6px;"
        )
        details_layout.addWidget(self.cover_image_label, 0, Qt.AlignmentFlag.AlignTop)

        self.details_layout = QFormLayout()
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setHorizontalSpacing(14)
        self.details_layout.setVerticalSpacing(10)
        self.release_date_label = QLabel()
        self.genres_label = QLabel()
        self.publisher_label = QLabel()
        self.developer_label = QLabel()
        self.rating_label = QLabel()
        for label in (
            self.release_date_label,
            self.genres_label,
            self.publisher_label,
            self.developer_label,
            self.rating_label,
        ):
            label.setWordWrap(True)
        self._add_row(self.details_layout, "Release Date", self.release_date_label)
        self._add_row(self.details_layout, "Genre(s)", self.genres_label)
        self._add_row(self.details_layout, "Publisher", self.publisher_label)
        self._add_row(self.details_layout, "Developer", self.developer_label)
        self._add_row(self.details_layout, "Rating", self.rating_label)
        details_layout.addLayout(self.details_layout, 1)

        # Summary group
        self.summary_group = self._make_group("Summary")
        summary_layout = QVBoxLayout(self.summary_group)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.summary_label)

        # Screenshots group
        self.screenshots_group = self._make_group("Screenshots")
        screenshots_layout = QVBoxLayout(self.screenshots_group)
        self.screenshots_scroll_area = QScrollArea()
        self.screenshots_scroll_area.setWidgetResizable(True)
        self.screenshots_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.screenshots_scroll_area.setFixedHeight(180)
        self.screenshots_widget = QWidget()
        self.screenshots_layout = QHBoxLayout(self.screenshots_widget)
        self.screenshots_layout.setSpacing(10)
        self.screenshots_scroll_area.setWidget(self.screenshots_widget)
        screenshots_layout.addWidget(self.screenshots_scroll_area)

        self.main_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.details_group)
        self.main_layout.addWidget(self.summary_group)
        self.main_layout.addWidget(self.screenshots_group)
        self.main_layout.addStretch(1)

        self.clear_info()

    @staticmethod
    def _make_group(title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(group_box_style())
        return group

    @staticmethod
    def _add_row(form: QFormLayout, label_text: str, field_widget: QLabel):
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {muted_text_color()};")
        form.addRow(label, field_widget)

    def clear_info(self):
        """Resets the view to its default state."""
        self.cover_image_label.clear()
        self.release_date_label.setText("-")
        self.genres_label.setText("-")
        self.publisher_label.setText("-")
        self.developer_label.setText("-")
        self.rating_label.setText("-")
        self.summary_label.clear()
        self.details_group.hide()
        self.summary_group.hide()
        self.screenshots_group.hide()

        # Clear previous screenshots
        while self.screenshots_layout.count():
            child = self.screenshots_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def set_game_name(self, game_name: str):
        self.title_label.setText(game_name)

    def set_game_info(
        self,
        summary: str,
        cover_url: str,
        release_date: str = None,
        genres: str = None,
        publisher: str = None,
        developer: str = None,
        screenshot_urls: str = None,
        rating: int = None,
    ):
        self.clear_info()

        self.details_group.show()
        self.summary_group.show()
        self.summary_label.setText(summary)

        self.release_date_label.setText(release_date or "-")
        self.genres_label.setText(genres or "-")
        self.publisher_label.setText(publisher or "-")
        self.developer_label.setText(developer or "-")
        if rating is None or rating == 0:
            rating_str = "N/A"
        else:
            rating_str = f"{rating / 10:.1f} / 10"
        self.rating_label.setText(rating_str)

        if cover_url:
            self._load_image(cover_url, self._covers_cache_folder, self.on_cover_loaded)

        if screenshot_urls is not None and screenshot_urls != "[]":
            urls = json.loads(screenshot_urls)
            self.screenshots_group.show()
            for url in urls:
                self._load_image(url, self._screenshots_cache_folder, self.on_screenshot_loaded)
        else:
            self.screenshots_group.hide()

    def _load_image(self, url: str, cache_folder: str, callback_slot):
        """Checks cache for an image and requests it if not found."""
        file_name = f"{hashlib.md5(url.encode()).hexdigest()}.jpg"
        local_path = os.path.join(cache_folder, file_name)

        if os.path.exists(local_path):
            pixmap = QPixmap(local_path)
            callback_slot(pixmap)
        else:
            request = QNetworkRequest(QUrl(url))
            # Store metadata in the request to retrieve it in the finished slot
            request.setAttribute(QNetworkRequest.Attribute.User, (local_path, callback_slot))
            self.network_manager.get(request)

    @Slot(QPixmap)
    def on_cover_loaded(self, pixmap: QPixmap):
        self.cover_image_label.setPixmap(
            pixmap.scaled(
                self.cover_image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    @Slot(QPixmap)
    def on_screenshot_loaded(self, pixmap: QPixmap):
        screenshot_label = QLabel()
        screenshot_label.setPixmap(
            pixmap.scaled(
                240,
                135,  # 16:9 aspect ratio
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.screenshots_layout.addWidget(screenshot_label)

    @Slot(QNetworkReply)
    def on_image_download_finished(self, reply: QNetworkReply):
        if reply.error() != QNetworkReply.NetworkError.NoError:
            print(f"Network Error: {reply.errorString()}")
            reply.deleteLater()
            return

        # Retrieve metadata from the request
        local_path, callback_slot = reply.request().attribute(QNetworkRequest.Attribute.User)

        image_data = reply.readAll()
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)

        # Save to cache and call the appropriate handler
        pixmap.save(local_path, "JPG", 90)
        callback_slot(pixmap)

        reply.deleteLater()
