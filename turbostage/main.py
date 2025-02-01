import importlib
import sys
from argparse import ArgumentParser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from turbostage.main_window import MainWindow


def show_splash_screen():
    # Load an image for the splash screen
    with importlib.resources.files("turbostage").joinpath("content/splash.jpg").open("rb") as file:
        pixmap = QPixmap()
        pixmap.loadFromData(file.read())

    # Create the splash screen with the image
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setMask(pixmap.mask())

    # Add text on top of the image
    splash.showMessage("Loading...", alignment=Qt.AlignBottom | Qt.AlignCenter, color=Qt.white)

    # Show the splash screen
    splash.show()

    return splash


def main():
    parser = ArgumentParser(description="TurboStage")
    parser.add_argument("-s", "--skip_splash", help="Skip splash screen", action="store_true")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow()

    if not args.skip_splash:
        splash = show_splash_screen()
        QTimer.singleShot(2000, lambda: [splash.close(), window.show()])
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
