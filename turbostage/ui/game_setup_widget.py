import os
import zipfile

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from turbostage import constants
from turbostage.db.game_database import GameDatabase
from turbostage.game_launcher import is_midi_device_available
from turbostage.ui.icons import load_icon
from turbostage.ui.theme import group_box_style, muted_text_color

NO_CONFIG_LABEL = "(none)"


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
        self._loading = False
        self._enabled = False
        self._game_id = None
        self._db = None
        self._versions = []

        self.version_id = -1
        self.selected_binary = None
        self.selected_config_binary = None
        self._pristine_binary = None
        self._pristine_config_binary = None
        self._pristine_cpu_index = 0
        self._pristine_midi_index = 0
        self._pristine_config = ""

        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("Select a game to configure it.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(f"color: {muted_text_color()}; font-size: 14px; padding: 24px;")
        self.layout.addWidget(self.empty_label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll_area.setWidget(self.content)
        self.layout.addWidget(self.scroll_area)

        # Version selector
        version_layout = QHBoxLayout()
        version_layout.addWidget(QLabel("Version:"))
        self.version_combobox = QComboBox()
        self.version_combobox.currentIndexChanged.connect(self._on_version_changed)
        version_layout.addWidget(self.version_combobox, 1)
        self.content_layout.addLayout(version_layout)

        # Game group
        self.game_group = self._make_group("Game")
        game_layout = QVBoxLayout(self.game_group)
        info_layout = QHBoxLayout()
        self.drive_icon_label = QLabel()
        info_layout.addWidget(self.drive_icon_label, 0, Qt.AlignmentFlag.AlignTop)
        self.game_info_label = QLabel()
        self.game_info_label.setWordWrap(True)
        self.game_info_label.setStyleSheet(f"color: {muted_text_color()};")
        info_layout.addWidget(self.game_info_label, 1)
        game_layout.addLayout(info_layout)
        self.binary_tabs = QTabWidget()
        self.binary_list_view = QListView()
        self.binary_list_model = BinaryListModel()
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.selected_binary = None
        self.binary_list_view.selectionModel().selectionChanged.connect(self._on_settings_changed)
        self.binary_list_view.setEnabled(False)
        self.config_binary_list_view = QListView()
        self.config_binary_list_model = BinaryListModel()
        self.config_binary_list_view.setModel(self.config_binary_list_model)
        self.config_binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.config_binary_list_view.selectionModel().selectionChanged.connect(self._on_settings_changed)
        self.config_binary_list_view.setEnabled(False)
        self.binary_tabs.addTab(self.binary_list_view, load_icon("executable"), "Game executable")
        self.binary_tabs.addTab(self.config_binary_list_view, load_icon("installer"), "Config executable")
        self.binary_tabs.setMinimumHeight(160)
        game_layout.addWidget(self.binary_tabs)
        self.content_layout.addWidget(self.game_group)

        # Performance group
        self.performance_group = self._make_group("Performance")
        performance_layout = QVBoxLayout(self.performance_group)
        performance_layout.addLayout(self._icon_row("cpu", "CPU"))
        self.cpu_combobox = QComboBox()
        self.cpu_combobox.addItems(list(constants.CPU_CYCLES.keys()))
        self.cpu_combobox.currentIndexChanged.connect(self._on_settings_changed)
        self.cpu_combobox.setEnabled(False)
        performance_layout.addWidget(self.cpu_combobox)
        performance_layout.addLayout(self._icon_row("midi", "MIDI Device"))
        self.midi_combobox = QComboBox()
        self.midi_combobox.addItems(list(constants.MIDI_DEVICE.keys()))
        self.midi_combobox.currentIndexChanged.connect(self._on_settings_changed)
        self.midi_combobox.setEnabled(False)
        performance_layout.addWidget(self.midi_combobox)
        self.content_layout.addWidget(self.performance_group)

        # Advanced group (collapsible)
        self.advanced_group = self._make_group("Advanced (extra DOSBox config)", checkable=True)
        advanced_layout = QVBoxLayout(self.advanced_group)
        self.advanced_content = QWidget()
        advanced_inner_layout = QVBoxLayout(self.advanced_content)
        advanced_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.dosbox_config_text = QTextEdit()
        self.dosbox_config_text.setMinimumHeight(120)
        self.dosbox_config_text.setPlaceholderText("Enter custom DOSBox configuration here...")
        self.dosbox_config_text.textChanged.connect(self._on_settings_changed)
        self.dosbox_config_text.setEnabled(False)
        advanced_inner_layout.addWidget(self.dosbox_config_text)
        advanced_layout.addWidget(self.advanced_content)
        self.advanced_group.toggled.connect(self._on_advanced_toggled)
        self.advanced_group.setChecked(False)
        self.content_layout.addWidget(self.advanced_group)

        self.content_layout.addStretch(1)

        # Footer buttons
        footer_layout = QHBoxLayout()
        footer_layout.addStretch(1)
        self.reset_button = QPushButton("Reset")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._on_reset)
        footer_layout.addWidget(self.reset_button)
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save)
        footer_layout.addWidget(self.save_button)
        self.content_layout.addLayout(footer_layout)

        self._set_empty_state(True)

    @staticmethod
    def _make_group(title, checkable=False):
        group = QGroupBox(title)
        group.setCheckable(checkable)
        group.setStyleSheet(group_box_style())
        return group

    @staticmethod
    def _icon_row(icon_name: str, text: str):
        layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(load_icon(icon_name).pixmap(16, 16))
        layout.addWidget(icon_label)
        layout.addWidget(QLabel(text))
        layout.addStretch(1)
        return layout

    def _set_empty_state(self, empty: bool):
        self.empty_label.setVisible(empty)
        self.scroll_area.setVisible(not empty)

    def set_game(self, game_id: int | None, db: GameDatabase):
        enabled = game_id is not None
        self._enabled = enabled
        self._game_id = game_id
        self._db = db

        self._set_empty_state(not enabled)
        self.binary_list_view.setEnabled(enabled)
        self.config_binary_list_view.setEnabled(enabled)
        self.cpu_combobox.setEnabled(enabled)
        self.midi_combobox.setEnabled(enabled)
        self.version_combobox.setEnabled(enabled)
        self.dosbox_config_text.setEnabled(enabled and self.advanced_group.isChecked())

        if not enabled:
            self._versions = []
            self.version_id = -1
            self.selected_binary = None
            self.selected_config_binary = None
            self.version_combobox.clear()
            self.binary_list_model.set_binaries([])
            self.config_binary_list_model.set_binaries([])
            self.game_info_label.clear()
            self.drive_icon_label.clear()
            self.save_button.setEnabled(False)
            self.reset_button.setEnabled(False)
            return

        versions = db.get_all_game_versions(game_id, detailed=True)

        if not versions:
            raise RuntimeError(f"Unable to get game details for '{game_id}'")

        self._versions = versions
        self._populate_version_combo()
        self._load_version(versions[0])

    def _populate_version_combo(self):
        self.version_combobox.blockSignals(True)
        self.version_combobox.clear()
        for index, version in enumerate(self._versions):
            self.version_combobox.addItem(version.version_name or f"Version {index + 1}")
        self.version_combobox.setCurrentIndex(0)
        self.version_combobox.blockSignals(False)

    def _on_version_changed(self, index: int):
        if self._loading or not self._versions or index < 0:
            return
        self._load_version(self._versions[index])

    def _load_version(self, version_details):
        self._loading = True
        try:
            self.version_id = version_details.version_id
            game_binary = version_details.executable
            game_config = version_details.config
            cpu_cycles = version_details.cycles
            midi_device = version_details.midi_device or 0
            game_archive = version_details.archive

            archive_type = self._db.get_archive_type(self.version_id)
            requires_install = self._db.get_requires_install(self.version_id)
            is_installed = False
            install_path = None
            if archive_type == "iso" and requires_install:
                is_installed, install_path = self._db.get_installation_status(self.version_id)

            warning = None
            binaries = []
            settings = QSettings("jberclaz", "TurboStage")
            mt32_roms_path = str(settings.value("app/mt32_path", ""))
            soundcanvas_roms_path = str(settings.value("app/soundcanvas_path", ""))
            try:
                if is_installed and install_path:
                    binaries = self._list_binaries_from_dir(install_path)
                else:
                    games_path = str(settings.value("app/games_path", ""))
                    game_archive_path = os.path.join(games_path, game_archive)
                    binaries = self._list_binaries(game_archive_path)
            except (FileNotFoundError, zipfile.BadZipFile, OSError) as e:
                binaries = []
                warning = f"Unable to read game archive: {e}"

            # Revert MIDI device to None if ROMs are not available
            if not is_midi_device_available(midi_device, mt32_roms_path, soundcanvas_roms_path):
                midi_device = 0

            self.binary_list_model.set_binaries(binaries)
            self.config_binary_list_model.set_binaries([NO_CONFIG_LABEL] + binaries)

            self._update_game_info(version_details, archive_type, requires_install, is_installed, warning)

            self._select_binary(game_binary)
            self._select_config_binary(version_details.config_executable)
            self._set_game_config(cpu_cycles, midi_device, game_config)
            self._capture_pristine()
        finally:
            self._loading = False

    def _update_game_info(
        self,
        version_details,
        archive_type,
        requires_install,
        is_installed,
        warning=None,
    ):
        if archive_type == "iso":
            if requires_install:
                status = "ISO (installed)" if is_installed else "ISO (requires installation)"
                drive_icon = "harddrive" if is_installed else "cdrom"
            else:
                status = "ISO"
                drive_icon = "cdrom"
        else:
            status = "ZIP archive"
            drive_icon = "floppy"

        self.drive_icon_label.setPixmap(load_icon(drive_icon).pixmap(32, 32))

        lines = [
            f"Version: {version_details.version_name}",
            f"Archive: {version_details.archive}",
            f"Type: {status}",
        ]
        if warning:
            lines.append(warning)
        self.game_info_label.setText("\n".join(lines))

    def set_new_game(self, game_archive: str):
        self._enabled = True
        self._set_empty_state(False)
        self.version_combobox.setEnabled(False)
        binaries = self._list_binaries(game_archive)
        self.binary_list_model.set_binaries(binaries)
        self.config_binary_list_model.set_binaries([NO_CONFIG_LABEL] + binaries)
        self.binary_list_view.setEnabled(True)
        self.config_binary_list_view.setEnabled(True)
        self.cpu_combobox.setEnabled(True)
        self.dosbox_config_text.setEnabled(True)
        self.version_id = -1
        self.selected_binary = None
        self.selected_config_binary = None
        self._versions = []
        self._capture_pristine()

    def enable_button(self, enabled: bool):
        self.save_button.setEnabled(enabled)

    @staticmethod
    def _list_binaries(game_archive: str):
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
        return binaries

    @staticmethod
    def _list_binaries_from_dir(directory: str):
        binaries = []
        for root, dirs, files in os.walk(directory):
            for f in files:
                if f.lower().endswith((".exe", ".bat", ".com")):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, directory)
                    binaries.append(rel_path)
        return binaries

    @staticmethod
    def populates_binary_list(game_archive: str, list_model):
        list_model.set_binaries(GameSetupWidget._list_binaries(game_archive))

    @staticmethod
    def populates_binary_list_from_dir(directory: str, list_model):
        list_model.set_binaries(GameSetupWidget._list_binaries_from_dir(directory))

    def _set_game_config(self, cpu_cycles, midi_device, game_config):
        if cpu_cycles is not None:
            index = list(constants.CPU_CYCLES.values()).index(cpu_cycles)
            self.cpu_combobox.setCurrentIndex(index)
        else:
            self.cpu_combobox.setCurrentIndex(0)

        if midi_device is not None and midi_device in constants.MIDI_DEVICE.values():
            index = list(constants.MIDI_DEVICE.values()).index(midi_device)
            self.midi_combobox.setCurrentIndex(index)
        else:
            self.midi_combobox.setCurrentIndex(0)

        self.dosbox_config_text.setPlainText(game_config or "")

    @staticmethod
    def _select_value(list_view, list_model, value):
        if value is None:
            return False
        for row in range(list_model.rowCount()):
            index = list_model.index(row, 0)
            item_data = list_model.data(index, Qt.DisplayRole)
            if item_data == value:
                list_view.selectionModel().select(index, QItemSelectionModel.Select)
                return True
        return False

    def _select_binary(self, game_binary):
        if self._select_value(self.binary_list_view, self.binary_list_model, game_binary):
            self.selected_binary = game_binary
        else:
            self.selected_binary = None

    def _select_config_binary(self, config_binary):
        value = config_binary if config_binary else NO_CONFIG_LABEL
        if not self._select_value(self.config_binary_list_view, self.config_binary_list_model, value):
            self._select_value(
                self.config_binary_list_view,
                self.config_binary_list_model,
                NO_CONFIG_LABEL,
            )
            value = NO_CONFIG_LABEL
        self.selected_config_binary = value

    def _capture_pristine(self):
        self._pristine_binary = self.selected_binary
        self._pristine_config_binary = self.selected_config_binary
        self._pristine_cpu_index = self.cpu_combobox.currentIndex()
        self._pristine_midi_index = self.midi_combobox.currentIndex()
        self._pristine_config = self.dosbox_config_text.toPlainText()
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)

    def _on_advanced_toggled(self, checked: bool):
        self.advanced_content.setVisible(checked)
        self.dosbox_config_text.setEnabled(checked and self._enabled)

    def _on_settings_changed(self):
        if self._loading:
            return
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            self.selected_binary = self.binary_list_model.binaries[selected_index[0].row()]
        config_index = self.config_binary_list_view.selectedIndexes()
        if config_index:
            self.selected_config_binary = self.config_binary_list_model.binaries[config_index[0].row()]
        if self._auto_save_enable:
            self.enable_button(True)
        self.reset_button.setEnabled(True)
        self.settings_changed.emit()

    def _on_reset(self):
        self._loading = True
        try:
            self._select_binary(self._pristine_binary)
            self._select_config_binary(self._pristine_config_binary)
            self.cpu_combobox.setCurrentIndex(self._pristine_cpu_index)
            self.midi_combobox.setCurrentIndex(self._pristine_midi_index)
            self.dosbox_config_text.setPlainText(self._pristine_config)
            self.selected_binary = self._pristine_binary
            self.selected_config_binary = self._pristine_config_binary
        finally:
            self._loading = False
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)

    def _on_save(self):
        self._capture_pristine()
        self.settings_applied.emit()

    @property
    def cpu_cycles(self) -> int:
        return constants.CPU_CYCLES[self.cpu_combobox.currentText()]

    @property
    def midi_device(self) -> int:
        return constants.MIDI_DEVICE[self.midi_combobox.currentText()]

    @property
    def config_executable(self) -> str | None:
        if self.selected_config_binary == NO_CONFIG_LABEL:
            return None
        return self.selected_config_binary
