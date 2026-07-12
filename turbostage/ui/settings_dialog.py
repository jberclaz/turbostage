import glob
import lzma
import os
import plistlib
import subprocess
import tarfile
import tempfile
from zipfile import ZipFile

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from turbostage import constants, utils
from turbostage.ui.clickable_line_edit import ClickableLineEdit
from turbostage.ui.download_dialog import DownloaderDialog


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.setModal(True)

        self.settings = QSettings("jberclaz", "TurboStage")

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.full_screen_checkbox = QCheckBox("Play game in full screen", self)
        self.full_screen_checkbox.setChecked(utils.to_bool(self.settings.value("app/full_screen", False)))
        form_layout.addRow(self.full_screen_checkbox)

        self.show_downloadable_checkbox = QCheckBox("Show downloadable games in library", self)
        self.show_downloadable_checkbox.setChecked(
            utils.to_bool(self.settings.value("app/show_downloadable", True))
        )
        form_layout.addRow(self.show_downloadable_checkbox)
        self.layout.addLayout(form_layout)

        self.emulator_path_input = ClickableLineEdit(self)
        emulator_path = str(self.settings.value("app/emulator_path", ""))
        self.emulator_path_input.setText(emulator_path)
        self.emulator_path_input.clicked.connect(self._select_emulator)
        self.emu_download_button = QPushButton("Download", self)
        self.emu_download_button.clicked.connect(self._download_emulator)
        self.emu_download_button.setEnabled(emulator_path == "")
        emulator_layout = QHBoxLayout()
        emulator_layout.addWidget(self.emulator_path_input)
        emulator_layout.addWidget(self.emu_download_button)
        form_layout.addRow("Emulator Path", emulator_layout)

        self.games_path_input = ClickableLineEdit(self)
        self.games_path_input.setText(str(self.settings.value("app/games_path", "")))
        self.games_path_input.clicked.connect(
            lambda: self._select_directory(self.games_path_input, "Select the Games folder")
        )
        form_layout.addRow("Games Path", self.games_path_input)

        self.mt32_path_input = ClickableLineEdit(self)
        mt32_roms_path = str(self.settings.value("app/mt32_path", ""))
        self.mt32_path_input.setText(mt32_roms_path)
        self.mt32_path_input.clicked.connect(
            lambda: self._select_directory(self.mt32_path_input, "Select the MT-32 ROMs folder")
        )
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
        self.settings.setValue("app/show_downloadable", self.show_downloadable_checkbox.isChecked())
        self.settings.setValue("app/emulator_path", self.emulator_path_input.text())
        self.settings.setValue("app/games_path", self.games_path_input.text())
        self.settings.setValue("app/mt32_path", self.mt32_path_input.text())
        super().accept()

    def reject(self):
        super().reject()

    def _select_emulator(self):
        os_name = utils.get_os()
        if os_name == "Windows":
            target_executable = "dosbox.exe"
        elif os_name in ["Linux", "Darwin"]:
            target_executable = "dosbox"
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select DosBox Staging binary", "", f"Executable Files ({target_executable});;All Files (*)"
        )
        if file_path:
            self.emulator_path_input.setText(file_path)
            version = utils.get_dosbox_version(file_path)
            if version != constants.SUPPORTED_DOSBOX_VERSION:
                QMessageBox.warning(
                    self,
                    "DosBox version not supported",
                    f"Your version of DosBox ({version}) is not supported by this frontend and may not work correctly.",
                    QMessageBox.Ok,
                )

    def _select_directory(self, target_widget, dialog_title):
        folder = QFileDialog.getExistingDirectory(self, dialog_title, "", QFileDialog.ShowDirsOnly)
        if folder:
            target_widget.setText(folder)

    def _download_mt32_roms(self):
        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        mt32_roms_path = os.path.join(app_data_folder, "mt32_roms")
        os.makedirs(mt32_roms_path, exist_ok=True)

        download_dialog = DownloaderDialog(self, "Download MT-32 roms")
        download_dialog.start_download(constants.MT32_ROMS_DOWNLOAD_URL)
        if not download_dialog.exec():
            return

        with ZipFile(download_dialog.data_buffer, "r") as zip_ref:
            zip_ref.extractall(mt32_roms_path)

        self.mt32_path_input.setText(mt32_roms_path)

    def _download_emulator(self):
        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        emulator_path = os.path.join(app_data_folder, "dosbox")
        os.makedirs(emulator_path, exist_ok=True)

        download_dialog = DownloaderDialog(self, "Download DosBox")
        os_name = utils.get_os()
        if os_name == "Linux":
            dosbox_url = constants.DOSBOX_STAGING_LINUX
        elif os_name == "Windows":
            dosbox_url = constants.DOSBOX_STAGING_WINDOWS
        elif os_name == "Darwin":
            dosbox_url = constants.DOSBOX_STAGING_MACOS
        download_dialog.start_download(dosbox_url)
        if not download_dialog.exec():
            return

        if os_name == "Linux":
            with lzma.open(download_dialog.data_buffer, "rb") as f:
                with tarfile.open(fileobj=f, mode="r|") as tar:  # Open the tar within lzma
                    tar.extractall(path=emulator_path)
                    for filename in tar.getnames():
                        if filename.endswith("/dosbox"):
                            executable = filename
                            break
        elif os_name == "Windows":
            with ZipFile(download_dialog.data_buffer, "r") as zip_ref:
                zip_ref.extractall(emulator_path)
                for filename in zip_ref.namelist():
                    if filename.endswith("/dosbox.exe"):
                        executable = filename
                        break
        elif os_name == "Darwin":
            with tempfile.NamedTemporaryFile(suffix=".dmg", delete=False) as tmp_dmg:
                tmp_dmg.write(download_dialog.data_buffer.getvalue())
                dmg_path = tmp_dmg.name
            try:
                result = subprocess.run(
                    ["hdiutil", "attach", "-plist", "-nobrowse", "-mountrandom", "/tmp", dmg_path],
                    capture_output=True, text=True, check=True,
                )
                plist = plistlib.loads(result.stdout.encode())
                mount_point = None
                for entity in plist.get("system-entities", []):
                    if "mount-point" in entity:
                        mount_point = entity["mount-point"]
                        break
                if mount_point:
                    app_bundles = glob.glob(os.path.join(mount_point, "*.app"))
                    if app_bundles:
                        app_bundle = app_bundles[0]
                        target_app = os.path.join(emulator_path, os.path.basename(app_bundle))
                        subprocess.run(["cp", "-R", app_bundle, target_app], check=True)
                        macos_dir = os.path.join(target_app, "Contents", "MacOS")
                        executables = os.listdir(macos_dir)
                        executable = os.path.join(
                            os.path.basename(app_bundle),
                            "Contents", "MacOS", executables[0],
                        ) if executables else ""
                    subprocess.run(["hdiutil", "detach", mount_point], check=True)
            finally:
                os.unlink(dmg_path)
        self.emulator_path_input.setText(os.path.join(emulator_path, executable))
