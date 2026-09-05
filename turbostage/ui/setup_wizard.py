import glob
import importlib
import lzma
import os
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
from zipfile import ZipFile

from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from turbostage import constants, utils
from turbostage.ui.download_dialog import DownloaderDialog
from turbostage.ui.icons import load_icon
from turbostage.ui.theme import muted_text_color

SETUP_COMPLETED_KEY = "app/setup_completed"


def is_setup_completed(settings: QSettings | None = None) -> bool:
    settings = settings or QSettings("jberclaz", "TurboStage")
    try:
        return utils.to_bool(settings.value(SETUP_COMPLETED_KEY, False))
    except RuntimeError:
        return False


def count_game_archives(folder: str) -> int:
    if not folder or not os.path.isdir(folder):
        return 0
    try:
        return sum(1 for f in os.listdir(folder) if f.lower().endswith((".zip", ".iso")))
    except OSError:
        return 0


def validate_emulator(path: str) -> tuple[bool, str]:
    """Check an emulator path. Returns (ok, version_or_message)."""
    if not path:
        return False, "No emulator selected yet."
    if not os.path.isfile(path):
        return False, "File not found."
    version = utils.get_dosbox_version(path)
    if not version:
        return False, "Found, but version could not be determined."
    if version != constants.SUPPORTED_DOSBOX_VERSION:
        return True, f"Found version {version} (recommended: {constants.SUPPORTED_DOSBOX_VERSION})."
    return True, f"Found DOSBox Staging {version} — ready."


class WelcomePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Welcome to TurboStage")
        self.setSubTitle("Your DOS classics, ready to play in a few clicks.")
        layout = QVBoxLayout(self)
        info = QLabel(
            "This quick setup will:\n\n"
            "1. Install DOSBox Staging (the emulator)\n"
            "2. Choose where your games live\n"
            "3. Optionally set up classic MT-32 / Sound Canvas music\n"
            "4. Fetch the game database and scan your collection\n\n"
            "It takes about 2 minutes. You can change everything later in File > Settings."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        hint = QLabel("Tip: you can re-run this wizard anytime via File > Setup Wizard.")
        hint.setStyleSheet(f"color: {muted_text_color()};")
        hint.setWordWrap(True)
        layout.addWidget(hint)


class EmulatorPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Install the emulator")
        self.setSubTitle("TurboStage needs DOSBox Staging to run your games.")
        settings = QSettings("jberclaz", "TurboStage")
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.path_field = QLineEdit(str(settings.value("app/emulator_path", "")))
        self.path_field.setReadOnly(True)
        self.path_field.textChanged.connect(self._on_changed)
        row.addWidget(self.path_field, 1)
        browse_button = QPushButton(load_icon("folder"), "Browse…")
        browse_button.clicked.connect(self._select_emulator)
        row.addWidget(browse_button)
        download_button = QPushButton(load_icon("download"), "Download")
        download_button.clicked.connect(self._download_emulator)
        row.addWidget(download_button)
        layout.addLayout(row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._on_changed()

    def _on_changed(self):
        ok, message = validate_emulator(self.path_field.text())
        color = "#3da55d" if ok else muted_text_color()
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color};")
        self.completeChanged.emit()

    def isComplete(self):
        ok, _ = validate_emulator(self.path_field.text())
        return ok

    def _select_emulator(self):
        os_name = utils.get_os()
        target = "dosbox.exe" if os_name == "Windows" else "dosbox"
        current = self.path_field.text()
        start_dir = os.path.dirname(current) if current else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select DOSBox Staging binary",
            start_dir,
            f"Executable Files ({target});;All Files (*)",
        )
        if file_path:
            self.path_field.setText(file_path)
            version = utils.get_dosbox_version(file_path)
            if version and version != constants.SUPPORTED_DOSBOX_VERSION:
                QMessageBox.warning(
                    self,
                    "DOSBox version",
                    f"DOSBox {version} may work, but TurboStage is tuned for " f"{constants.SUPPORTED_DOSBOX_VERSION}.",
                    QMessageBox.Ok,
                )

    def _download_emulator(self):
        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        emulator_path = os.path.join(app_data_folder, "dosbox")
        os.makedirs(emulator_path, exist_ok=True)

        os_name = utils.get_os()
        if os_name == "Linux":
            dosbox_url = constants.DOSBOX_STAGING_LINUX
        elif os_name == "Windows":
            dosbox_url = constants.DOSBOX_STAGING_WINDOWS
        elif os_name == "Darwin":
            dosbox_url = constants.DOSBOX_STAGING_MACOS
        else:
            QMessageBox.warning(self, "Unsupported OS", f"Unsupported operating system: {os_name}")
            return

        dialog = DownloaderDialog(self, "Download DOSBox")
        dialog.start_download(dosbox_url)
        if not dialog.exec():
            return

        try:
            executable = ""
            if os_name == "Linux":
                with lzma.open(dialog.data_buffer, "rb") as f:
                    with tarfile.open(fileobj=f, mode="r|") as tar:
                        tar.extractall(path=emulator_path)
                        for filename in tar.getnames():
                            if filename.endswith("/dosbox"):
                                executable = filename
                                break
            elif os_name == "Windows":
                with ZipFile(dialog.data_buffer, "r") as zip_ref:
                    zip_ref.extractall(emulator_path)
                    for filename in zip_ref.namelist():
                        if filename.endswith("/dosbox.exe"):
                            executable = filename
                            break
            elif os_name == "Darwin":
                with tempfile.NamedTemporaryFile(suffix=".dmg", delete=False) as tmp_dmg:
                    tmp_dmg.write(dialog.data_buffer.getvalue())
                    dmg_path = tmp_dmg.name
                try:
                    result = subprocess.run(
                        ["hdiutil", "attach", "-plist", "-nobrowse", "-mountrandom", "/tmp", dmg_path],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    plist = plistlib.loads(result.stdout.encode())
                    mount_point = next(
                        (e["mount-point"] for e in plist.get("system-entities", []) if "mount-point" in e),
                        None,
                    )
                    if mount_point:
                        bundles = glob.glob(os.path.join(mount_point, "*.app"))
                        if bundles:
                            target_app = os.path.join(emulator_path, os.path.basename(bundles[0]))
                            subprocess.run(["cp", "-R", bundles[0], target_app], check=True)
                            executables = os.listdir(os.path.join(target_app, "Contents", "MacOS"))
                            if executables:
                                executable = os.path.join(
                                    os.path.basename(bundles[0]), "Contents", "MacOS", executables[0]
                                )
                        subprocess.run(["hdiutil", "detach", mount_point], check=True)
                finally:
                    os.unlink(dmg_path)
        except Exception as e:  # noqa: BLE001 - show any download/extract failure to the user
            QMessageBox.critical(self, "Download failed", f"Could not install DOSBox:\n{e}")
            return

        if executable:
            self.path_field.setText(os.path.join(emulator_path, executable))
        else:
            QMessageBox.warning(self, "Download finished", "Download finished but the executable was not found.")


class GamesFolderPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Where are your games?")
        self.setSubTitle("Drop your .zip or .iso files in one folder — TurboStage does the rest.")
        settings = QSettings("jberclaz", "TurboStage")
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.path_field = QLineEdit(str(settings.value("app/games_path", "")))
        self.path_field.setReadOnly(True)
        self.path_field.textChanged.connect(self._on_changed)
        row.addWidget(self.path_field, 1)
        browse_button = QPushButton(load_icon("folder"), "Browse…")
        browse_button.clicked.connect(self._select_directory)
        row.addWidget(browse_button)
        layout.addLayout(row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        hint = QLabel("Don't have games yet? No problem — you can download free ones from the library later.")
        hint.setStyleSheet(f"color: {muted_text_color()};")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._on_changed()

    def _on_changed(self):
        path = self.path_field.text()
        if not path:
            self.status_label.setText("Pick a folder to continue.")
        elif not os.path.isdir(path):
            self.status_label.setText("That folder doesn't exist.")
        else:
            count = count_game_archives(path)
            self.status_label.setText(
                f"Found {count} game file{'s' if count != 1 else ''} in this folder."
                if count
                else "Folder looks good — no games in it yet."
            )
        self.status_label.setStyleSheet(f"color: {muted_text_color()};")
        self.completeChanged.emit()

    def isComplete(self):
        path = self.path_field.text()
        return bool(path) and os.path.isdir(path)

    def _select_directory(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select the Games folder", self.path_field.text(), QFileDialog.ShowDirsOnly
        )
        if folder:
            self.path_field.setText(folder)


class MusicPage(QWizardPage):
    """Optional MT-32 / Sound Canvas ROM setup. Always complete — everything is skippable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Classic music (optional)")
        self.setSubTitle("Add Roland MT-32 / Sound Canvas ROMs for authentic sound. Skip for now if you like.")
        settings = QSettings("jberclaz", "TurboStage")
        layout = QVBoxLayout(self)

        self.mt32_field = self._add_rom_row(
            layout, "MT-32 ROMs", str(settings.value("app/mt32_path", "")), self._download_mt32_roms
        )
        self.soundcanvas_field = self._add_rom_row(
            layout, "Sound Canvas ROMs", str(settings.value("app/soundcanvas_path", "")), self._download_sc_roms
        )
        hint = QLabel("You can set this up later in File > Settings. Games still play without it.")
        hint.setStyleSheet(f"color: {muted_text_color()};")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def isComplete(self):
        return True

    def _add_rom_row(self, layout, title, current, download_slot):
        layout.addWidget(QLabel(title))
        row = QHBoxLayout()
        field = QLineEdit(current)
        field.setReadOnly(True)
        field.setPlaceholderText("Not set up (optional)")
        row.addWidget(field, 1)
        browse_button = QPushButton(load_icon("folder"), "Browse…")
        browse_button.clicked.connect(lambda: self._select_directory(field, f"Select the {title} folder"))
        row.addWidget(browse_button)
        download_button = QPushButton(load_icon("download"), "Download")
        download_button.clicked.connect(lambda: download_slot(field))
        row.addWidget(download_button)
        layout.addLayout(row)
        return field

    def _select_directory(self, target, title):
        folder = QFileDialog.getExistingDirectory(self, title, target.text(), QFileDialog.ShowDirsOnly)
        if folder:
            target.setText(folder)

    def _download_mt32_roms(self, target):
        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        mt32_path = os.path.join(app_data_folder, "mt32_roms")
        os.makedirs(mt32_path, exist_ok=True)
        dialog = DownloaderDialog(self, "Download MT-32 ROMs")
        dialog.start_download(constants.MT32_ROMS_DOWNLOAD_URL)
        if not dialog.exec():
            return
        with ZipFile(dialog.data_buffer, "r") as zip_ref:
            zip_ref.extractall(mt32_path)
        target.setText(mt32_path)

    def _download_sc_roms(self, target):
        app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        sc_path = os.path.join(app_data_folder, "soundcanvas_roms")
        os.makedirs(sc_path, exist_ok=True)
        dialog = DownloaderDialog(self, "Download SoundCanvas ROMs")
        dialog.start_download(constants.SOUNDCANVAS_ROMS_DOWNLOAD_URL)
        if not dialog.exec():
            return
        with tempfile.TemporaryDirectory() as tmp_dir:
            with ZipFile(dialog.data_buffer, "r") as zip_ref:
                zip_ref.extractall(tmp_dir)
            roms_src = os.path.join(tmp_dir, "Nuked-SC55-CLAP-ROM-files", "Nuked-SC55-Resources", "ROMs")
            for item in os.listdir(roms_src):
                src, dst = os.path.join(roms_src, item), os.path.join(sc_path, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        target.setText(sc_path)


class FinishPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("You're all set!")
        self.setSubTitle("One last step — let TurboStage build your library.")
        layout = QVBoxLayout(self)
        self.update_db_checkbox = QCheckBox("Update game database (recommended)")
        self.update_db_checkbox.setChecked(True)
        layout.addWidget(self.update_db_checkbox)
        self.scan_checkbox = QCheckBox("Scan my games folder now")
        self.scan_checkbox.setChecked(True)
        layout.addWidget(self.scan_checkbox)
        hint = QLabel("Click Finish and start playing. Double-click any game to launch it.")
        hint.setStyleSheet(f"color: {muted_text_color()};")
        hint.setWordWrap(True)
        layout.addWidget(hint)


class SetupWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to TurboStage")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(620, 480)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self._emulator_page = EmulatorPage(self)
        self._games_page = GamesFolderPage(self)
        self._music_page = MusicPage(self)
        self._finish_page = FinishPage(self)

        self.setPage(0, WelcomePage(self))
        self.setPage(1, self._emulator_page)
        self.setPage(2, self._games_page)
        self.setPage(3, self._music_page)
        self.setPage(4, self._finish_page)

        with importlib.resources.files("turbostage").joinpath("content/icon.png").open("rb") as file:
            logo = QPixmap()
            logo.loadFromData(file.read())
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, logo)
        with importlib.resources.files("turbostage").joinpath("content/splash.jpg").open("rb") as file:
            splash = QPixmap()
            splash.loadFromData(file.read())
            watermark = splash.scaled(
                220,
                420,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(QWizard.WizardPixmap.WatermarkPixmap, watermark)

    @property
    def emulator_path(self) -> str:
        return self._emulator_page.path_field.text()

    @property
    def games_path(self) -> str:
        return self._games_page.path_field.text()

    @property
    def mt32_path(self) -> str:
        return self._music_page.mt32_field.text()

    @property
    def soundcanvas_path(self) -> str:
        return self._music_page.soundcanvas_field.text()

    @property
    def do_update_db(self) -> bool:
        return self._finish_page.update_db_checkbox.isChecked()

    @property
    def do_scan(self) -> bool:
        return self._finish_page.scan_checkbox.isChecked()

    def accept(self):
        settings = QSettings("jberclaz", "TurboStage")
        settings.setValue("app/emulator_path", self.emulator_path)
        settings.setValue("app/games_path", self.games_path)
        if self.mt32_path:
            settings.setValue("app/mt32_path", self.mt32_path)
        if self.soundcanvas_path:
            settings.setValue("app/soundcanvas_path", self.soundcanvas_path)
        settings.setValue(SETUP_COMPLETED_KEY, True)
        super().accept()
