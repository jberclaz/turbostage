from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLineEdit


class ClickableLineEdit(QLineEdit):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, event: QMouseEvent):
        # Only trigger the file dialog when the left mouse button is clicked
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)
