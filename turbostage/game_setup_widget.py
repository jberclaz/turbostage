import os
import sqlite3
import zipfile

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QSettings, Qt
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
    def __init__(self, save_slot):
        super().__init__()

        self.layout = QVBoxLayout(self)

        self.pick_label = QLabel("Game executable")
        self.layout.addWidget(self.pick_label)
        self.binary_list_view = QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.selected_binary = None
        self.binary_list_view.selectionModel().selectionChanged.connect(self._on_selection_change)
        self.layout.addWidget(self.binary_list_view)

        self.layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        label = QLabel("CPU")
        self.layout.addWidget(label)
        self.cpu_combobox = QComboBox()
        self.cpu_combobox.addItems(list(constants.CPU_CYCLES.keys()))
        self.cpu_combobox.currentIndexChanged.connect(self._on_selection_change)
        self.layout.addWidget(self.cpu_combobox)

        self.layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.config_label = QLabel("Extra DosBox config (optional)")
        self.layout.addWidget(self.config_label)
        self.dosbox_config_text = QTextEdit(self)
        self.dosbox_config_text.setPlaceholderText("Enter custom DOSBox configuration here...")
        self.dosbox_config_text.textChanged.connect(self._on_selection_change)
        self.layout.addWidget(self.dosbox_config_text)

        self.version_id = -1
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)
        self.save_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.save_button.clicked.connect(self._on_save)
        self.layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.save_slot = save_slot

    def set_game(self, game_id: int, db_path: str):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT v.executable, lv.archive, v.config, v.cycles, v.version, v.id
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id
            WHERE g.igdb_id = ?
            """,
            (game_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        if len(rows) != 1:
            raise RuntimeError(f"Unable to get game details for '{game_id}'")
        game_binary, game_archive, game_config, cpu_cycles, game_version, self.version_id = rows[0]
        settings = QSettings("jberclaz", "TurboStage")
        games_path = str(settings.value("app/games_path", ""))
        game_archive_path = os.path.join(games_path, game_archive)

        self.populates_binary_list(game_archive_path, self.binary_list_model)
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

        if cpu_cycles is not None:
            index = list(constants.CPU_CYCLES.values()).index(cpu_cycles)
            self.cpu_combobox.setCurrentIndex(index)

        if game_config is not None:
            self.dosbox_config_text.setText(game_config)

        self.save_button.setEnabled(False)

    @staticmethod
    def populates_binary_list(game_archive: str, list_model):
        binaries = []
        with zipfile.ZipFile(game_archive, "r") as zf:
            for info in zf.infolist():
                _, extension = os.path.splitext(info.filename)
                if extension.lower() not in [".exe", ".bat", ".com"]:
                    continue
                binaries.append(info.filename)
        list_model.set_binaries(binaries)

    def _on_selection_change(self):
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            self.selected_binary = self.binary_list_model.binaries[selected_index[0].row()]
        self.save_button.setEnabled(True)

    def _on_save(self):
        self.save_button.setEnabled(False)
        self.save_slot.emit()

    @property
    def cpu_cycles(self) -> int:
        return constants.CPU_CYCLES[self.cpu_combobox.currentText()]
