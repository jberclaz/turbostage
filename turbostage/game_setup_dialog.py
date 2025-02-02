from PySide6 import QtWidgets

from turbostage.game_setup_widget import BinaryListModel, GameSetupWidget


class GameSetupDialog(QtWidgets.QDialog):
    def __init__(self, game_archive: str):
        super().__init__()

        self.setWindowTitle("Game Setup")
        self.setModal(True)

        self.layout = QtWidgets.QVBoxLayout(self)

        self.pick_label = QtWidgets.QLabel("Pick the game's setup command")
        self.layout.addWidget(self.pick_label)
        self.binary_list_view = QtWidgets.QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QtWidgets.QListView.SingleSelection)
        GameSetupWidget.populates_binary_list(game_archive, self.binary_list_model)
        self.binary_list_view.selectionModel().selectionChanged.connect(self._on_selection_change)
        self.layout.addWidget(self.binary_list_view)

        self.configure_button = QtWidgets.QPushButton("Setup")
        self.configure_button.setEnabled(False)
        self.configure_button.clicked.connect(self._on_configure)
        self.layout.addWidget(self.configure_button)

        self.selected_binary = None

    def _on_selection_change(self):
        selected_index = self.binary_list_view.selectedIndexes()
        if selected_index:
            self.selected_binary = self.binary_list_model.binaries[selected_index[0].row()]
        self.configure_button.setEnabled(True)

    def _on_configure(self):
        self.accept()
