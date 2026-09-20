import os

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from turbostage import constants, utils
from turbostage.provisioning import (
    app_subdir,
    dosbox_download_url,
    extract_dosbox_archive,
    extract_mt32_roms,
    extract_soundcanvas_roms,
)
from turbostage.ui.download_dialog import DownloaderDialog
from turbostage.ui.icons import load_icon
from turbostage.ui.theme import group_box_style


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.setModal(True)

        self.settings = QSettings("jberclaz", "TurboStage")

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.full_screen_checkbox = QCheckBox("Play game in full screen", self)
        self.full_screen_checkbox.setIcon(load_icon("monitor"))
        self.full_screen_checkbox.setChecked(utils.to_bool(self.settings.value("app/full_screen", False)))
        form_layout.addRow(self.full_screen_checkbox)

        self.show_downloadable_checkbox = QCheckBox("Show downloadable games in library", self)
        self.show_downloadable_checkbox.setIcon(load_icon("download"))
        self.show_downloadable_checkbox.setChecked(utils.to_bool(self.settings.value("app/show_downloadable", True)))
        form_layout.addRow(self.show_downloadable_checkbox)

        self.grid_view_checkbox = QCheckBox("Display games as a grid of cover images", self)
        self.grid_view_checkbox.setChecked(utils.to_bool(self.settings.value("app/grid_view", True)))
        form_layout.addRow(self.grid_view_checkbox)

        self.disk_noise_checkbox = QCheckBox("Enable disk noise emulation", self)
        self.disk_noise_checkbox.setIcon(load_icon("speaker"))
        self.disk_noise_checkbox.setChecked(utils.to_bool(self.settings.value("app/disk_noise", False)))
        form_layout.addRow(self.disk_noise_checkbox)
        self.layout.addLayout(form_layout)

        self.emulator_path_input = self._make_path_field(str(self.settings.value("app/emulator_path", "")))
        emulator_browse_button = QPushButton(load_icon("folder"), "Browse…", self)
        emulator_browse_button.clicked.connect(self._select_emulator)
        self.emu_download_button = QPushButton(load_icon("download"), "Download", self)
        self.emu_download_button.clicked.connect(self._download_emulator)
        self.layout.addWidget(
            self._make_path_group(
                "computer",
                "Emulator Path",
                self.emulator_path_input,
                [emulator_browse_button, self.emu_download_button],
            )
        )

        self.games_path_input = self._make_path_field(str(self.settings.value("app/games_path", "")))
        games_browse_button = QPushButton(load_icon("folder"), "Browse…", self)
        games_browse_button.clicked.connect(
            lambda: self._select_directory(self.games_path_input, "Select the Games folder")
        )
        self.layout.addWidget(
            self._make_path_group("folder", "Games Path", self.games_path_input, [games_browse_button])
        )

        self.mt32_path_input = self._make_path_field(str(self.settings.value("app/mt32_path", "")))
        mt32_browse_button = QPushButton(load_icon("folder"), "Browse…", self)
        mt32_browse_button.clicked.connect(
            lambda: self._select_directory(self.mt32_path_input, "Select the MT-32 ROMs folder")
        )
        self.mt32_download_button = QPushButton(load_icon("download"), "Download", self)
        self.mt32_download_button.clicked.connect(self._download_mt32_roms)
        self.layout.addWidget(
            self._make_path_group(
                "midi",
                "MT-32 Roms Path",
                self.mt32_path_input,
                [mt32_browse_button, self.mt32_download_button],
            )
        )

        self.soundcanvas_path_input = self._make_path_field(str(self.settings.value("app/soundcanvas_path", "")))
        soundcanvas_browse_button = QPushButton(load_icon("folder"), "Browse…", self)
        soundcanvas_browse_button.clicked.connect(
            lambda: self._select_directory(self.soundcanvas_path_input, "Select the SoundCanvas ROMs folder")
        )
        self.soundcanvas_download_button = QPushButton(load_icon("download"), "Download", self)
        self.soundcanvas_download_button.clicked.connect(self._download_soundcanvas_roms)
        self.layout.addWidget(
            self._make_path_group(
                "midi",
                "SoundCanvas Roms Path",
                self.soundcanvas_path_input,
                [soundcanvas_browse_button, self.soundcanvas_download_button],
            )
        )

        button_box = QDialogButtonBox(self)
        button_box.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setIcon(load_icon("ok"))
        button_box.button(QDialogButtonBox.Cancel).setIcon(load_icon("cancel"))
        self.layout.addWidget(button_box)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def accept(self):
        self.settings.setValue("app/full_screen", self.full_screen_checkbox.isChecked())
        self.settings.setValue("app/show_downloadable", self.show_downloadable_checkbox.isChecked())
        self.settings.setValue("app/grid_view", self.grid_view_checkbox.isChecked())
        self.settings.setValue("app/disk_noise", self.disk_noise_checkbox.isChecked())
        self.settings.setValue("app/emulator_path", self.emulator_path_input.text())
        self.settings.setValue("app/games_path", self.games_path_input.text())
        self.settings.setValue("app/mt32_path", self.mt32_path_input.text())
        self.settings.setValue("app/soundcanvas_path", self.soundcanvas_path_input.text())
        super().accept()

    def reject(self):
        super().reject()

    def _make_path_field(self, text):
        field = QLineEdit(self)
        field.setReadOnly(True)
        field.setText(text)
        return field

    def _make_path_group(self, icon_name, title, field, buttons):
        group = QGroupBox(title, self)
        group.setStyleSheet(group_box_style())
        layout = QVBoxLayout(group)
        field_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(load_icon(icon_name).pixmap(16, 16))
        field_row.addWidget(icon_label)
        field_row.addWidget(field, 1)
        layout.addLayout(field_row)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(icon_label.pixmap().width() + field_row.spacing(), 0, 0, 0)
        for button in buttons:
            button_layout.addWidget(button)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)
        return group

    def _confirm_overwrite(self, title, message):
        return (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _select_emulator(self):
        os_name = utils.get_os()
        if os_name == "Windows":
            target_executable = "dosbox.exe"
        elif os_name in ["Linux", "Darwin"]:
            target_executable = "dosbox"
        current_path = self.emulator_path_input.text()
        start_dir = os.path.dirname(current_path) if current_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select DosBox Staging binary",
            start_dir,
            f"Executable Files ({target_executable});;All Files (*)",
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
        start_dir = target_widget.text() if target_widget.text() else ""
        folder = QFileDialog.getExistingDirectory(self, dialog_title, start_dir, QFileDialog.ShowDirsOnly)
        if folder:
            target_widget.setText(folder)

    def _download_mt32_roms(self):
        if self.mt32_path_input.text() and not self._confirm_overwrite(
            "Download MT-32 roms",
            "MT-32 roms are already configured.\nDownload and replace them?",
        ):
            return

        mt32_roms_path = app_subdir("mt32_roms")

        download_dialog = DownloaderDialog(self, "Download MT-32 roms")
        download_dialog.start_download(constants.MT32_ROMS_DOWNLOAD_URL)
        if not download_dialog.exec():
            return

        try:
            extract_mt32_roms(download_dialog.data_buffer, mt32_roms_path)
        except OSError as e:
            QMessageBox.critical(self, "Download failed", f"Could not install MT-32 ROMs:\n{e}")
            return

        self.mt32_path_input.setText(mt32_roms_path)

    def _download_soundcanvas_roms(self):
        if self.soundcanvas_path_input.text() and not self._confirm_overwrite(
            "Download SoundCanvas roms",
            "SoundCanvas roms are already configured.\nDownload and replace them?",
        ):
            return

        soundcanvas_roms_path = app_subdir("soundcanvas_roms")

        download_dialog = DownloaderDialog(self, "Download SoundCanvas roms")
        download_dialog.start_download(constants.SOUNDCANVAS_ROMS_DOWNLOAD_URL)
        if not download_dialog.exec():
            return

        try:
            extract_soundcanvas_roms(download_dialog.data_buffer, soundcanvas_roms_path)
        except OSError as e:
            QMessageBox.critical(self, "Download failed", f"Could not install SoundCanvas ROMs:\n{e}")
            return

        self.soundcanvas_path_input.setText(soundcanvas_roms_path)

    def _download_emulator(self):
        if self.emulator_path_input.text() and not self._confirm_overwrite(
            "Download DosBox",
            "A DosBox is already configured.\nDownload and replace it?",
        ):
            return

        emulator_path = app_subdir("dosbox")

        download_dialog = DownloaderDialog(self, "Download DosBox")
        os_name = utils.get_os()
        try:
            dosbox_url = dosbox_download_url(os_name)
        except OSError as e:
            QMessageBox.warning(self, "Unsupported OS", str(e))
            return
        download_dialog.start_download(dosbox_url)
        if not download_dialog.exec():
            return

        try:
            executable = extract_dosbox_archive(download_dialog.data_buffer, emulator_path, os_name)
        except OSError as e:
            QMessageBox.critical(self, "Download failed", f"Could not install DOSBox:\n{e}")
            return
        self.emulator_path_input.setText(os.path.join(emulator_path, executable))
