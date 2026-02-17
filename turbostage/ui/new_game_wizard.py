import importlib
import os

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListView,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from turbostage import constants, iso_utils
from turbostage.ui.game_setup_widget import BinaryListModel

EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".com"}


class NewGameWizard(QWizard):
    def __init__(self, igdb_client, game_archive_path: str, parent=None):
        super(NewGameWizard, self).__init__(parent)
        self.setWindowTitle("Add New Game")
        self.setWizardStyle(QWizard.ModernStyle)
        with importlib.resources.files("turbostage").joinpath("content/msdos_logo.png").open("rb") as file:
            pixmap = QPixmap()
            pixmap.loadFromData(file.read())
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)
        with importlib.resources.files("turbostage").joinpath("content/wizard.png").open("rb") as file:
            pixmap = QPixmap()
            pixmap.loadFromData(file.read())
            self.setPixmap(QWizard.WizardPixmap.WatermarkPixmap, pixmap)

        self._game_archive_path = game_archive_path
        self._is_iso = iso_utils.is_iso_file(game_archive_path)
        self._volume_label = None

        executables = self.get_executables_from_archive(game_archive_path)

        # Get volume label for ISO files to use as default version name
        if self._is_iso:
            self._volume_label = iso_utils.get_iso_volume_label(game_archive_path)

        self.addPage(GameTitlePage(igdb_client, os.path.basename(game_archive_path)))
        self.addPage(VersionPage(self._volume_label, self._is_iso))
        self.addPage(ExecutablePage(executables, is_iso=self._is_iso))
        # Only add ConfigPage for non-ISO or ISO without installation
        # For ISO with installation, the installation binary is selected in ExecutablePage
        self.addPage(ConfigPage(executables, is_iso=self._is_iso))
        self.addPage(CPUPage())
        self.addPage(DosBoxOptions())

    @property
    def game_title(self) -> str:
        return self.field("game.title")[0]

    @property
    def igdb_id(self) -> int:
        return self.field("game.title")[1]

    @property
    def game_version(self) -> str:
        version = self.field("game.version")
        return version if version else "default"

    @property
    def game_executable(self) -> str:
        exe = self.field("game.executable")
        return exe if exe else ""

    @property
    def game_config(self) -> str | None:
        return self.field("game.config_file")

    @property
    def cpu(self) -> int:
        return self.field("game.cpu")

    @property
    def dosbox_config(self) -> str:
        return self.field("game.extra_config")

    @property
    def requires_install(self) -> bool:
        return self.field("game.requires_install") if self._is_iso else False

    @staticmethod
    def get_executables_from_archive(game_archive: str) -> list[str]:
        if iso_utils.is_iso_file(game_archive):
            return iso_utils.list_executables_in_iso(game_archive)
        else:
            import zipfile

            with zipfile.ZipFile(game_archive, "r") as zf:
                return [
                    info.filename
                    for info in zf.infolist()
                    if os.path.splitext(info.filename)[1].lower() in EXECUTABLE_EXTENSIONS
                ]


class GameTitlePage(QWizardPage):
    def __init__(self, igdb_client, file_name, parent=None):
        super().__init__(parent)
        self.setTitle("Game title")
        self.setSubTitle("Search for the game title in the search box and pick the correct version")
        self._igdb_client = igdb_client

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.game_name_search_query = QLineEdit()
        self.game_name_search_query.returnPressed.connect(self._search_games_slot)
        form_layout.addRow("Search", self.game_name_search_query)
        layout.addLayout(form_layout)

        self.game_list_view = QListView(self)
        self.game_list_model = GameListModel()
        self.game_list_view.setModel(self.game_list_model)
        self.game_list_view.selectionModel().selectionChanged.connect(self._selection_changed)
        self.game_list_view.setSelectionMode(QListView.SingleSelection)
        layout.addWidget(self.game_list_view)
        self.setLayout(layout)

        base_name, _ = os.path.splitext(file_name)
        self._search_games(base_name)

        self.registerField("game.title*", self, "selected_title")

    @property
    def selected_title(self) -> str:
        selected_index = self.game_list_view.selectedIndexes()
        if selected_index:
            return self.game_list_model.games[selected_index[0].row()]
        return ""

    def _search_games_slot(self):
        self._search_games(self.game_name_search_query.text())

    def _search_games(self, search_query):
        response = self._igdb_client.search_games(search_query)
        game_names = [(row["name"], row["id"]) for row in response]
        self.game_list_model.set_games(game_names)
        self.game_list_view.clearSelection()

    def _selection_changed(self):
        self.setField("game.title", self.selected_title)
        self.completeChanged.emit()

    def isComplete(self):
        return len(self.game_list_view.selectedIndexes()) == 1


class VersionPage(QWizardPage):
    def __init__(self, volume_label: str | None = None, is_iso: bool = False, parent=None):
        super().__init__(parent)
        self._is_iso = is_iso
        self.setTitle("Game version")
        self.setSubTitle("Enter the game version")

        layout = QVBoxLayout(self)

        self.version_label = QLabel("Version name")
        self.version_name = QLineEdit(self)
        self.version_name.setPlaceholderText("Eg: 'vga', 'en', '1.2', ...")

        # Use volume label as default version name for ISO files
        if volume_label:
            self.version_name.setText(volume_label)

        layout.addWidget(self.version_label)
        layout.addWidget(self.version_name)

        # Add checkbox for ISO games that require HD installation
        if is_iso:
            self.install_checkbox = QCheckBox("Requires hard drive installation")
            self.install_checkbox.setToolTip(
                "Check this if the game needs to be installed to the hard drive before playing"
            )
            layout.addWidget(self.install_checkbox)
            self.registerField("game.requires_install", self.install_checkbox)

        self.setLayout(layout)

        self.registerField("game.version", self.version_name)


class ExecutablePage(QWizardPage):
    def __init__(self, executables: list[str], is_iso: bool = False, parent=None):
        super().__init__(parent)
        self._is_iso = is_iso
        self.setTitle("Game executable")
        self.setSubTitle("Pick the executable file to start the game")

        layout = QVBoxLayout(self)
        label = QLabel("Game executable")
        layout.addWidget(label)
        self.binary_list_view = QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_model.set_binaries(executables)
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.binary_list_view.selectionModel().selectionChanged.connect(self._selection_changed)
        layout.addWidget(self.binary_list_view)
        self.setLayout(layout)

        self.registerField("game.executable", self, "selected_executable")

    def initializePage(self):
        # Check if this is ISO with install mode - if so, game executable is optional
        requires_install = self.field("game.requires_install")
        if self._is_iso and requires_install:
            self.setSubTitle("Select the installation program (optional - can be selected after installation)")
            self.setTitle("Installation program")

    def isComplete(self):
        # If ISO with install, game executable is optional (will be selected after installation)
        requires_install = self.field("game.requires_install")
        if self._is_iso and requires_install:
            return True
        return len(self.binary_list_view.selectedIndexes()) == 1

    @property
    def selected_executable(self) -> str:
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            return self.binary_list_model.binaries[selected_index[0].row()]
        return ""

    def _selection_changed(self):
        self.setField("game.executable", self.selected_executable)
        self.completeChanged.emit()


class ConfigPage(QWizardPage):
    def __init__(self, executables: list[str], is_iso: bool = False, parent=None):
        super().__init__(parent)
        self._is_iso = is_iso
        self.setTitle("Game config")
        self.setSubTitle("Pick the executable file for game setup (optional)")

        layout = QVBoxLayout(self)
        self.label = QLabel("Configuration executable")
        layout.addWidget(self.label)
        self.binary_list_view = QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_model.set_binaries(executables)
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.selected_binary = None
        self.binary_list_view.selectionModel().selectionChanged.connect(self._selection_changed)
        layout.addWidget(self.binary_list_view)
        self.setLayout(layout)

        self.registerField("game.config_file", self, "selected_config")

    def initializePage(self):
        # For ISO with installation, skip this page (use ExecutablePage for installation program)
        if self._is_iso and self.field("game.requires_install"):
            self.setSkip(True)
            self.setSubTitle("Skipped for ISO with installation")
        else:
            self.setSkip(False)
            self.setSubTitle("Pick the executable file for game setup (optional)")
            self.label.setText("Configuration executable")

    @property
    def selected_config(self) -> str:
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            return self.binary_list_model.binaries[selected_index[0].row()]
        return ""

    def _selection_changed(self):
        self.setField("game.config_file", self.selected_config)


class CPUPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("CPU config")
        self.setSubTitle(
            "Pick the appropriate system to run the game. In most cases, you can leave it to 'auto'. This can be adjusted later."
        )

        layout = QVBoxLayout(self)
        label = QLabel("System CPU")
        layout.addWidget(label)
        self.cpu_combobox = QComboBox()
        self.cpu_combobox.addItems(list(constants.CPU_CYCLES.keys()))
        layout.addWidget(self.cpu_combobox)
        self.setLayout(layout)

        self.registerField("game.cpu", self.cpu_combobox)


class DosBoxOptions(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("DosBox options")
        self.setSubTitle("Add extra DosBox config for this game (optional)")

        layout = QVBoxLayout(self)
        self.dosbox_config_text = QTextEdit(self)
        self.dosbox_config_text.setPlaceholderText("Enter custom DOSBox configuration here...")
        self.dosbox_config_text.textChanged.connect(self._text_changed)
        layout.addWidget(self.dosbox_config_text)

        self.registerField("game.extra_config", self.dosbox_config_text)

    def _text_changed(self):
        self.setField("game.extra_config", self.dosbox_config_text.toPlainText())


class GameListModel(QAbstractListModel):
    def __init__(self, games=None):
        super().__init__()
        self.games = games or []

    def rowCount(self, parent=QModelIndex()):
        return len(self.games)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.games[index.row()][0]

    def set_games(self, games):
        self.beginResetModel()
        self.games = games
        self.endResetModel()
