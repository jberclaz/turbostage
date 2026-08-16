import importlib.resources
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


def load_icon(name: str) -> QIcon:
    """Load a bundled retro icon by its base name (without extension)."""
    path = importlib.resources.files("turbostage").joinpath("content", "icons", f"{name}.ico")
    return QIcon(str(path))


def icon_widget(name: str, text: str, parent: Optional[QWidget] = None) -> QWidget:
    """Build a compact widget with an icon followed by a text label."""
    widget = QWidget(parent)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    icon_label = QLabel()
    icon_label.setPixmap(load_icon(name).pixmap(16, 16))
    layout.addWidget(icon_label)
    layout.addWidget(QLabel(text))
    layout.addStretch(1)
    return widget
