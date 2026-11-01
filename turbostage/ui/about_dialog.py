import importlib.resources
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from turbostage import __version__
from turbostage.game_metadata import GameMetadataCatalog, MetadataUnavailable
from turbostage.ui.theme import muted_text_color

logger = logging.getLogger(__name__)

PROJECT_URL = "https://github.com/jberclaz/turbostage"
IGDB_URL = "https://www.igdb.com"
DOSBOX_STAGING_URL = "https://www.dosbox-staging.org"
QT_URL = "https://www.qt.io"


class AboutDialog(QDialog):
    def __init__(self, metadata: GameMetadataCatalog, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About TurboStage")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        with importlib.resources.files("turbostage").joinpath("content/icon.png").open("rb") as file:
            pixmap = QPixmap()
            pixmap.loadFromData(file.read())
        logo.setPixmap(pixmap)
        logo.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(logo)
        title = QLabel(
            f"<div style='font-size: 20px; font-weight: bold;'>TurboStage</div>"
            f"<div>Version {__version__}</div>"
            f"<div>A friendly frontend for DOSBox Staging.</div>"
            f"<div><a href='{PROJECT_URL}'>{PROJECT_URL}</a></div>"
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setOpenExternalLinks(True)
        title.setWordWrap(True)
        header.addWidget(title, 1)
        layout.addLayout(header)

        credits = QLabel(
            f"<p>Game information and images are provided by <a href='{IGDB_URL}'>IGDB.com</a>."
            f"{self._snapshot_note(metadata)}</p>"
            f"<p>Games run in <a href='{DOSBOX_STAGING_URL}'>DOSBox Staging</a> (GPL-2.0).<br>"
            f"User interface built with <a href='{QT_URL}'>Qt</a> and PySide6 (LGPL-3.0).</p>"
        )
        credits.setTextFormat(Qt.TextFormat.RichText)
        credits.setOpenExternalLinks(True)
        credits.setWordWrap(True)
        layout.addWidget(credits)

        license_label = QLabel("TurboStage is free software, released under the Apache License 2.0.")
        license_label.setWordWrap(True)
        license_label.setStyleSheet(f"color: {muted_text_color()};")
        layout.addWidget(license_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _snapshot_note(metadata: GameMetadataCatalog) -> str:
        try:
            generated_at = metadata.generated_at
        except MetadataUnavailable:
            logger.warning("Game metadata unavailable for the About dialog")
            return ""
        return f"<br>Game database snapshot: {generated_at}." if generated_at else ""
