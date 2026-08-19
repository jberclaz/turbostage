from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette


def is_dark_theme() -> bool:
    """Return True if the application is running with a dark color scheme."""
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    # The platform didn't report a scheme: infer it from the window background.
    window_color = QGuiApplication.palette().color(QPalette.ColorRole.Window)
    return window_color.lightness() < 128


def muted_text_color() -> str:
    """A secondary text color that stays readable in light and dark themes."""
    return "#a8a8a8" if is_dark_theme() else "#6e6e6e"


def border_color() -> str:
    """A subtle border color that stays visible in light and dark themes."""
    return "#4a4a4a" if is_dark_theme() else "#b8b8b8"


def group_box_style() -> str:
    """Stylesheet for a titled group box that adapts to the active theme."""
    return (
        "QGroupBox {"
        f" border: 1px solid {border_color()};"
        " border-radius: 6px;"
        " margin-top: 14px;"
        " padding-top: 8px;"
        "}"
        "QGroupBox::title {"
        " subcontrol-origin: margin;"
        " left: 12px;"
        " padding: 0 6px;"
        " font-weight: bold;"
        "}"
    )
