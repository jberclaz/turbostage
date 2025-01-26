import os
from io import BytesIO
from zipfile import ZipFile

import requests
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from turbostage import constants, utils
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

        self.mt32_path_input = ClickableLineEdit(self)
        mt32_roms_path = str(self.settings.value("app/mt32_path", ""))
        self.mt32_path_input.setText(mt32_roms_path)
        self.mt32_path_input.clicked.connect(self._select_mt32_path)
        self.mt32_download_button = QPushButton("Download", self)
        self.mt32_download_button.clicked.connect(self._download_mt32_roms)
        self.mt32_download_button.setEnabled(mt32_roms_path == "")
        mt32_layout = QHBoxLayout()
        mt32_layout.addWidget(self.mt32_path_input)
        mt32_layout.addWidget(self.mt32_download_button)
        form_layout.addRow("MT-32 Roms Path", mt32_layout)

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
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select DosBox Staging binary", "", "Executable Files (dosbox);;All Files (*)"
        )
        if file_path:
            self.emulator_path_input.setText(file_path)
            version = utils.get_dosbox_version(self.settings)
            if version != constants.SUPPORTED_DOSBOX_VERSION:
                QMessageBox.warning(
                    self,
                    "DosBox version not supported",
                    f"Your version of DosBox ({version}) is not supported by this frontend and may not work correctly.",
                    QMessageBox.OK,
                )

    def _select_games_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select the Games folder", "", QFileDialog.ShowDirsOnly)
        if folder:
            self.games_path_input.setText(folder)

    def _select_mt32_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select the MT-32 ROMs folder", "", QFileDialog.ShowDirsOnly)
        if folder:
            self.mt32_path_input.setText(folder)

    def _download_mt32_roms(self):
        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        mt32_roms_path = os.path.join(app_data_folder, "mt32_roms")
        os.makedirs(mt32_roms_path, exist_ok=True)
        self.settings.setValue("app/mt32_path", mt32_roms_path)

        response = requests.get(constants.MT32_ROMS_DOWNLOAD_URL)
        response.raise_for_status()
        with BytesIO(response.content) as zip_file_in_memory:
            with ZipFile(zip_file_in_memory, "r") as zip_ref:
                zip_ref.extractall(mt32_roms_path)

        self.mt32_path_input.setText(mt32_roms_path)

    @staticmethod
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() == "true"
