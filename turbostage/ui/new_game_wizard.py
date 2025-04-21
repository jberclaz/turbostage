from PySide6.QtWidgets import QWizard


class NewGameWizard(QWizard):
    def __init__(self, parent=None):
        super(NewGameWizard, self).__init__(parent)
        self.setWindowTitle("Add New Game")
        self.setWizardStyle(QWizard.ModernStyle)
