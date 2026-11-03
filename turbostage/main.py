import importlib
import logging
import os
import sys
from argparse import ArgumentParser

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from turbostage import app_paths, data_migration, utils
from turbostage.log_setup import setup_logging
from turbostage.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _fallback_splash_pixmap() -> QPixmap:
    """Solid-colour splash used when content/splash.jpg is missing/corrupt."""
    pixmap = QPixmap(480, 320)
    pixmap.fill(QColor("#20242c"))
    return pixmap


def show_splash_screen(app):
    # Load an image for the splash screen (missing/corrupt file falls back
    # to a solid pixmap instead of crashing on pixmap.mask()).
    pixmap = QPixmap()
    try:
        with importlib.resources.files("turbostage").joinpath("content/splash.jpg").open("rb") as file:
            pixmap.loadFromData(file.read())
    except (FileNotFoundError, IsADirectoryError, OSError) as e:
        logger.warning("Splash image unavailable, using fallback: %s", e)
    if pixmap.isNull():
        pixmap = _fallback_splash_pixmap()

    # Create the splash screen with the image
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setMask(pixmap.mask())

    # Add text on top of the image
    splash.showMessage("Loading...", alignment=Qt.AlignBottom | Qt.AlignCenter, color=Qt.white)

    # On macOS, QSplashScreen uses Qt::SplashScreen which doesn't
    # activate the application when launched from CLI, making the
    # splash invisible. Using Dialog|FramelessWindowHint works around this.
    if sys.platform == "darwin":
        splash.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

    # Show the splash screen
    splash.show()
    app.processEvents()

    return splash


def main():
    parser = ArgumentParser(description="TurboStage")
    parser.add_argument("-s", "--skip_splash", help="Skip splash screen", action="store_true")
    args = parser.parse_args()

    if hasattr(sys, "_MEIPASS") and sys.platform == "linux" and "QT_QPA_PLATFORMTHEME" not in os.environ:
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"

    app = QApplication(sys.argv)
    # Wayland app id / X11 WM class; must match the installed .desktop file
    # so desktops show the right icon (otherwise the window is "python3").
    app.setDesktopFileName("io.github.jberclaz.turbostage")
    # Before anything opens the library or the log: older versions kept them
    # directly in the shared data folder.
    migration = data_migration.migrate_legacy_data(QSettings("jberclaz", "TurboStage"))
    if not migration.use_new_folder:
        app_paths.use_legacy_root()
    setup_logging()
    migration.log()
    utils.apply_flatpak_defaults(QSettings("jberclaz", "TurboStage"))
    if utils.is_flatpak():
        # Use Qt's own file dialogs, not the desktop's file-chooser portal: the
        # portal can fail without ever answering (e.g. a typed folder that
        # doesn't exist), leaving the app waiting forever. Qt's dialog also
        # shows exactly the folders the sandbox can access.
        app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)

    splash = None
    if not args.skip_splash:
        splash = show_splash_screen(app)

    window = MainWindow()
    window.show()
    if splash:
        splash.finish(window)

    # Only once the splash is gone: it stays on top, so a first-run wizard
    # opened while it is up hides behind it (Windows) and the app looks stuck.
    QTimer.singleShot(0, window.maybe_show_setup_wizard)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
