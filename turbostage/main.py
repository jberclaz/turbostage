import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from turbostage.main_window import MainWindow


def show_splash_screen():
    # Load an image for the splash screen
    pixmap = QPixmap("content/turbostage.jpg")  # Replace with the path to your image

    # Create the splash screen with the image
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setMask(pixmap.mask())

    # Add text on top of the image
    splash.showMessage("Loading...", alignment=Qt.AlignBottom | Qt.AlignCenter, color=Qt.white)

    # Show the splash screen
    splash.show()

    return splash


def main():
    app = QApplication(sys.argv)

    splash = show_splash_screen()
    window = MainWindow()

    QTimer.singleShot(200, lambda: [splash.close(), window.show()])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
