from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QCheckBox, QDialogButtonBox


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.setModal(True)

        self.settings = QSettings("jberclaz", "TurboStage")

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.full_screen_checkbox = QCheckBox("Play game in full screen", self)
        self.full_screen_checkbox.setChecked(self._to_bool(self.settings.value("app/full_screen", False)))
        form_layout.addRow(self.full_screen_checkbox)
        self.layout.addLayout(form_layout)

        button_box = QDialogButtonBox(self)
        button_box.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.layout.addWidget(button_box)

        # Connect buttons to appropriate methods
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def accept(self):
        self.settings.setValue("app/full_screen", self.full_screen_checkbox.isChecked())
        super().accept()

    def reject(self):
        super().reject()

    @staticmethod
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() == "true"
