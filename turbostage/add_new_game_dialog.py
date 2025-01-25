from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QListView, QPushButton, QVBoxLayout

from turbostage.igdb_client import IgdbClient


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


class AddNewGameDialog(QDialog):
    def __init__(self, igdb_client, parent):
        super().__init__()
        self.setWindowTitle("Add new game")
        self.setModal(True)
        self._igdb_client = igdb_client

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.game_name_search_query = QLineEdit()
        self.game_name_search_query.returnPressed.connect(self._search_games)
        form_layout.addRow("Game name", self.game_name_search_query)
        self.layout.addLayout(form_layout)

        self.game_list_view = QListView(self)
        self.game_list_model = GameListModel()
        self.game_list_view.setModel(self.game_list_model)
        self.game_list_view.doubleClicked.connect(self._on_game_selected)
        self.game_list_view.selectionModel().selectionChanged.connect(self._on_selection_change)
        self.game_list_view.setSelectionMode(QListView.SingleSelection)
        self.layout.addWidget(self.game_list_view)

        self.select_button = QPushButton("Select Game")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self._on_game_selected)
        self.layout.addWidget(self.select_button)

        self.selected_game = None

        parent_geom = parent.geometry()
        self.move(
            parent_geom.x() + (parent_geom.width() - self.width()) // 2,
            parent_geom.y() + (parent_geom.height() - self.height()) // 2,
        )

    def _search_games(self):
        response = self._igdb_client.search(
            "games", ["name"], self.game_name_search_query.text(), f"platforms=({IgdbClient.DOS_PLATFORM_ID})"
        )
        game_names = [(row["name"], row["id"]) for row in response]
        self.game_list_model.set_games(game_names)
        self.game_list_view.clearSelection()
        self.select_button.setEnabled(False)

    def _on_game_selected(self):
        selected_index = self.game_list_view.selectedIndexes()
        if selected_index:
            game_name, game_id = self.game_list_model.games[selected_index[0].row()]
            self.selected_game = (game_name, game_id)
            self.accept()

    def _on_selection_change(self):
        self.select_button.setEnabled(True)
