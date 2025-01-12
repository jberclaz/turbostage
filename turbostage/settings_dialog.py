from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QCheckBox, QDialogButtonBox, QLineEdit, QFileDialog

from turbostage.clickable_line_edit import ClickableLineEdit


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

        self.emulator_path_input = ClickableLineEdit(self)
        self.emulator_path_input.setText(self.settings.value("app/emulator_path", ""))
        self.emulator_path_input.clicked.connect(self._select_emulator)
        form_layout.addRow("Emulator Path", self.emulator_path_input)

        self.games_path_input = ClickableLineEdit(self)
        self.games_path_input.setText(self.settings.value("app/games_path", ""))
        self.games_path_input.clicked.connect(self._select_games_path)
        form_layout.addRow("Games Path", self.games_path_input)

        button_box = QDialogButtonBox(self)
        button_box.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.layout.addWidget(button_box)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def accept(self):
        self.settings.setValue("app/full_screen", self.full_screen_checkbox.isChecked())
        self.settings.setValue("app/emulator_path", self.emulator_path_input.text())
        self.settings.setValue("app/games_path", self.games_path_input.text())
        super().accept()

    def reject(self):
        super().reject()

    def _select_emulator(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select DosBox Staging binary", "", "Executable Files (dosbox);;All Files (*)")
        if file_path:
            self.emulator_path_input.setText(file_path)
            # TODO: test and validate version

    def _select_games_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select the Games folder", "", QFileDialog.ShowDirsOnly)
        if folder:
            self.games_path_input.setText(folder)

    @staticmethod
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() == "true"
