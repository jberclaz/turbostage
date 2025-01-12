from PySide6.QtWidgets import QDialog


class AddNewGameDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Add new game")
        self.setModal(True)