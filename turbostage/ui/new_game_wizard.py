import importlib
import os

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QLineEdit, QListView, QVBoxLayout, QWizard, QWizardPage

from turbostage.igdb_client import IgdbClient
from turbostage.ui.add_new_game_dialog import GameListModel


class NewGameWizard(QWizard):
    def __init__(self, igdb_client, file_name, parent=None):
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

        self.addPage(GameTitlePage(igdb_client, file_name))
        self.addPage(ExecutablePage())


class GameTitlePage(QWizardPage):
    def __init__(self, igdb_client, file_name, parent=None):
        super().__init__(parent)
        self.setTitle("Game title")
        self.setSubTitle("Search for the game title in the search box and pick the correct version")
        self._igdb_client = igdb_client

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.game_name_search_query = QLineEdit()
        self.game_name_search_query.returnPressed.connect(self._search_games_slot)
        form_layout.addRow("Search", self.game_name_search_query)
        self.layout.addLayout(form_layout)

        self.game_list_view = QListView(self)
        self.game_list_model = GameListModel()
        self.game_list_view.setModel(self.game_list_model)
        self.game_list_view.selectionModel().selectionChanged.connect(self.completeChanged)
        self.game_list_view.setSelectionMode(QListView.SingleSelection)
        self.layout.addWidget(self.game_list_view)

        base_name, _ = os.path.splitext(file_name)
        self._search_games(base_name)

    def _search_games_slot(self):
        self._search_games(self.game_name_search_query.text())

    def _search_games(self, search_query):
        response = self._igdb_client.search(
            "games", ["name"], search_query, f"platforms=({IgdbClient.DOS_PLATFORM_ID})"
        )
        game_names = [(row["name"], row["id"]) for row in response]
        self.game_list_model.set_games(game_names)
        self.game_list_view.clearSelection()

    def isComplete(self):
        return len(self.game_list_view.selectedIndexes()) == 1


class ExecutablePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Game executable")
        self.setSubTitle("Pick the executable file to start the game")
