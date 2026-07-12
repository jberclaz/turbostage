import os
import zipfile

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from turbostage import constants
from turbostage.db.game_database import GameDatabase


class BinaryListModel(QAbstractListModel):
    def __init__(self, binaries=None):
        super().__init__()
        self.binaries = binaries or []

    def rowCount(self, parent=QModelIndex()):
        return len(self.binaries)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.binaries[index.row()]

    def set_binaries(self, binaries):
        self.beginResetModel()
        self.binaries = binaries
        self.endResetModel()


class GameSetupWidget(QWidget):
    settings_applied = Signal()
    settings_changed = Signal()

    def __init__(self, auto_save_enable=True):
        super().__init__()

        self._auto_save_enable = auto_save_enable

        self.layout = QVBoxLayout(self)

        self.pick_label = QLabel("Game executable")
        self.layout.addWidget(self.pick_label)
        self.binary_list_view = QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.selected_binary = None
        self.binary_list_view.selectionModel().selectionChanged.connect(self._on_settings_changed)
        self.binary_list_view.setEnabled(False)
        self.layout.addWidget(self.binary_list_view)

        self.layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        label = QLabel("CPU")
        self.layout.addWidget(label)
        self.cpu_combobox = QComboBox()
        self.cpu_combobox.addItems(list(constants.CPU_CYCLES.keys()))
        self.cpu_combobox.currentIndexChanged.connect(self._on_settings_changed)
        self.cpu_combobox.setEnabled(False)
        self.layout.addWidget(self.cpu_combobox)

        self.layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.config_label = QLabel("Extra DosBox config (optional)")
        self.layout.addWidget(self.config_label)
        self.dosbox_config_text = QTextEdit(self)
        self.dosbox_config_text.setPlaceholderText("Enter custom DOSBox configuration here...")
        self.dosbox_config_text.textChanged.connect(self._on_settings_changed)
        self.dosbox_config_text.setEnabled(False)
        self.layout.addWidget(self.dosbox_config_text)

        self.version_id = -1
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)
        self.save_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.save_button.clicked.connect(self._on_save)
        self.layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignRight)

    def set_game(self, game_id: int | None, db: GameDatabase):
        enabled = game_id is not None
        self.binary_list_view.setEnabled(enabled)
        self.cpu_combobox.setEnabled(enabled)
        self.dosbox_config_text.setEnabled(enabled)
        if not enabled:
            return

        versions = db.get_all_game_versions(game_id, detailed=True)

        if not versions:
            raise RuntimeError(f"Unable to get game details for '{game_id}'")

        # Use the first version for now
        # TODO: Allow user to select which version to configure
        version_details = versions[0]

        # Access the version details from the GameVersionInfo object
        self.version_id = version_details.version_id
        game_binary = version_details.executable
        game_config = version_details.config
        cpu_cycles = version_details.cycles
        game_archive = version_details.archive

        settings = QSettings("jberclaz", "TurboStage")
        games_path = str(settings.value("app/games_path", ""))
        game_archive_path = os.path.join(games_path, game_archive)

        # For installed ISO games, list binaries from the install directory instead of the archive
        archive_type = db.get_archive_type(self.version_id)
        if archive_type == "iso":
            requires_install = db.get_requires_install(self.version_id)
            if requires_install:
                is_installed, install_path = db.get_installation_status(self.version_id)
                if is_installed and install_path:
                    self.populates_binary_list_from_dir(install_path, self.binary_list_model)
                    self._select_binary(game_binary)
                    self._set_game_config(cpu_cycles, game_config)
                    self.save_button.setEnabled(False)
                    return

        self.populates_binary_list(game_archive_path, self.binary_list_model)
        self._select_binary(game_binary)
        self._set_game_config(cpu_cycles, game_config)
        self.save_button.setEnabled(False)

    def set_new_game(self, game_archive: str):
        self.populates_binary_list(game_archive, self.binary_list_model)
        self.binary_list_view.setEnabled(True)
        self.cpu_combobox.setEnabled(True)
        self.dosbox_config_text.setEnabled(True)

    def enable_button(self, enabled: bool):
        self.save_button.setEnabled(enabled)

    @staticmethod
    def populates_binary_list(game_archive: str, list_model):
        binaries = []
        from turbostage import iso_utils

        if iso_utils.is_iso_file(game_archive):
            binaries = iso_utils.list_executables_in_iso(game_archive)
        else:
            with zipfile.ZipFile(game_archive, "r") as zf:
                for info in zf.infolist():
                    _, extension = os.path.splitext(info.filename)
                    if extension.lower() not in [".exe", ".bat", ".com"]:
                        continue
                    binaries.append(info.filename)
        list_model.set_binaries(binaries)

    @staticmethod
    def populates_binary_list_from_dir(directory: str, list_model):
        binaries = []
        for root, dirs, files in os.walk(directory):
            for f in files:
                if f.lower().endswith((".exe", ".bat", ".com")):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, directory)
                    binaries.append(rel_path)
        list_model.set_binaries(binaries)

    def _set_game_config(self, cpu_cycles, game_config):
        if cpu_cycles is not None:
            index = list(constants.CPU_CYCLES.values()).index(cpu_cycles)
            self.cpu_combobox.setCurrentIndex(index)
        else:
            self.cpu_combobox.setCurrentIndex(0)

        self.dosbox_config_text.setPlainText(game_config or "")

    def _select_binary(self, game_binary):
        if game_binary is not None:
            for row in range(self.binary_list_model.rowCount()):
                index = self.binary_list_model.index(row, 0)
                item_data = self.binary_list_model.data(index, Qt.DisplayRole)
                if item_data == game_binary:
                    self.binary_list_view.selectionModel().select(index, QItemSelectionModel.Select)
                    self.selected_binary = game_binary
                    break
        else:
            self.selected_binary = None

    def _on_settings_changed(self):
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            self.selected_binary = self.binary_list_model.binaries[selected_index[0].row()]
        if self._auto_save_enable:
            self.enable_button(True)
        self.settings_changed.emit()

    def _on_save(self):
        self.save_button.setEnabled(False)
        self.settings_applied.emit()

    @property
    def cpu_cycles(self) -> int:
        return constants.CPU_CYCLES[self.cpu_combobox.currentText()]
