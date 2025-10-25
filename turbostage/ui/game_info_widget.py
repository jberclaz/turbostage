import hashlib
import os

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget


class GameInfoWidget(QWidget):
    def __init__(self):
        super().__init__()

        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self._covers_cache_folder = os.path.join(app_data_folder, "covers")
        os.makedirs(self._covers_cache_folder, exist_ok=True)

        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_image_download_finished)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- UI Widgets ---
        self.title_label = QLabel("Select a game to see details here.")
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        self.title_label.setWordWrap(True)

        # Header section (cover + details)
        self.header_layout = QHBoxLayout()
        self.cover_image_label = QLabel()
        self.cover_image_label.setFixedSize(180, 240)  # A bit larger cover
        self.cover_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_image_label.setStyleSheet("background-color: #2c2c2c; border-radius: 5px;")

        self.details_layout = QFormLayout()
        self.details_layout.setContentsMargins(10, 0, 0, 0)
        self.release_date_label = QLabel()
        self.genres_label = QLabel()
        self.publisher_label = QLabel()
        self.developer_label = QLabel()  # New field
        self.rating_label = QLabel()  # New field

        self.details_layout.addRow("Release Date:", self.release_date_label)
        self.details_layout.addRow("Genre(s):", self.genres_label)
        self.details_layout.addRow("Publisher:", self.publisher_label)
        self.details_layout.addRow("Developer:", self.developer_label)
        self.details_layout.addRow("Rating:", self.rating_label)

        self.header_layout.addWidget(self.cover_image_label)
        self.header_layout.addLayout(self.details_layout)
        self.header_layout.addStretch()

        # Summary section
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("margin-top: 15px;")

        # Screenshots section
        self.screenshots_title = QLabel("Screenshots")
        self.screenshots_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 15px;")
        self.screenshots_scroll_area = QScrollArea()
        self.screenshots_scroll_area.setWidgetResizable(True)
        self.screenshots_scroll_area.setFixedHeight(120)  # Fixed height for the gallery
        self.screenshots_widget = QWidget()
        self.screenshots_layout = QHBoxLayout(self.screenshots_widget)
        self.screenshots_scroll_area.setWidget(self.screenshots_widget)

        # Add widgets to main layout
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addLayout(self.header_layout)
        self.main_layout.addWidget(self.summary_label)
        self.main_layout.addWidget(self.screenshots_title)
        self.main_layout.addWidget(self.screenshots_scroll_area)
        self.main_layout.addStretch()  # Pushes everything up

        self.clear_info()

    def clear_info(self):
        """Resets the view to its default state."""
        self.cover_image_label.clear()
        self.release_date_label.setText("-")
        self.genres_label.setText("-")
        self.publisher_label.setText("-")
        self.developer_label.setText("-")
        self.rating_label.setText("-")
        self.summary_label.hide()
        self.screenshots_title.hide()
        self.screenshots_scroll_area.hide()

        # Clear previous screenshots
        while self.screenshots_layout.count():
            child = self.screenshots_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def set_game_name(self, game_name: str):
        self.title_label.setText(game_name)

    def set_game_info(
        self, summary: str, cover_url: str, release_date: str = None, genres: str = None, publisher: str = None
    ):
        self.clear_info()

        self.summary_label.setText(summary)
        self.summary_label.show()

        # Populate details, with fallbacks for None
        self.release_date_label.setText(release_date or "-")
        self.genres_label.setText(genres)
        self.publisher_label.setText(publisher or "-")

        if cover_url:
            self._load_image(cover_url, self._covers_cache_folder, self.on_cover_loaded)

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
                160,
                90,  # 16:9 aspect ratio
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
