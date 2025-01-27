import os
import zipfile

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
)


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


class ConfigureGameDialog(QDialog):
    def __init__(
        self,
        game_name: str,
        game_id: int,
        game_archive: str,
        version: str | None = None,
        binary: str | None = None,
        config: str | None = None,
        add: bool = True,
    ):
        super().__init__()
        self._game_name = game_name
        self._game_id = game_id
        self._game_archive = game_archive

        self.setWindowTitle("Configure game")
        self.setModal(True)

        self.layout = QVBoxLayout(self)

        self.version_label = QLabel("Version name")
        self.version_name = QLineEdit(self)
        self.version_name.setPlaceholderText("Eg: 'vga', 'en', '1.2, ...")
        if version is not None:
            self.version_name.setText(version)
        self.version_name.textChanged.connect(self._on_version_change)
        self.layout.addWidget(self.version_label)
        self.layout.addWidget(self.version_name)

        self.layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.pick_label = QLabel("Pick the game's executable")
        self.layout.addWidget(self.pick_label)
        self.binary_list_view = QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.populates_binary_list(game_archive, self.binary_list_model)
        if binary is not None:
            for row in range(self.binary_list_model.rowCount()):
                index = self.binary_list_model.index(row, 0)
                item_data = self.binary_list_model.data(index, Qt.DisplayRole)
                if item_data == binary:
                    self.binary_list_view.selectionModel().select(index, QItemSelectionModel.Select)
                    break
        self.binary_list_view.selectionModel().selectionChanged.connect(self._on_selection_change)
        self.layout.addWidget(self.binary_list_view)

        self.layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.config_label = QLabel("Extra DosBox config (optional)")
        self.layout.addWidget(self.config_label)
        self.dosbox_config_text = QTextEdit(self)
        self.dosbox_config_text.setPlaceholderText("Enter custom DOSBox configuration here...")
        if config is not None:
            self.dosbox_config_text.setText(config)
        self.layout.addWidget(self.dosbox_config_text)

        self.add_button = QPushButton("Add game")
        if not add:
            self.add_button.setText("Update game")
        self.add_button.setEnabled(not add)
        self.add_button.clicked.connect(self._on_add_game)
        self.layout.addWidget(self.add_button)

        self.selected_binary = None

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

    def _on_add_game(self):
        self.accept()

    def _on_selection_change(self):
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            self.selected_binary = self.binary_list_model.binaries[selected_index[0].row()]
        self.add_button.setEnabled(self.version_name.text() != "")

    def _on_version_change(self):
        if self.version_name.text() == "":
            self.add_button.setEnabled(False)
            return
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            self.add_button.setEnabled(True)
