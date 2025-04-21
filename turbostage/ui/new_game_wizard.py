import importlib
import os
import zipfile

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QListView, QVBoxLayout, QWizard, QWizardPage

from turbostage.igdb_client import IgdbClient
from turbostage.ui.add_new_game_dialog import GameListModel
from turbostage.ui.game_setup_widget import BinaryListModel, GameSetupWidget


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

        self.addPage(GameTitlePage(igdb_client, os.path.basename(game_archive_path)))
        self.addPage(VersionPage())
        self.addPage(ExecutablePage(game_archive_path))
        self.addPage(ConfigPage())
        self.addPage(CPUPage())
        self.addPage(DosBoxOptions())


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
        self.game_list_view.selectionModel().selectionChanged.connect(self.completeChanged)
        self.game_list_view.setSelectionMode(QListView.SingleSelection)
        layout.addWidget(self.game_list_view)
        self.setLayout(layout)

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


class VersionPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Game version")
        self.setSubTitle("Enter the game version")

        layout = QVBoxLayout(self)

        self.version_label = QLabel("Version name")
        self.version_name = QLineEdit(self)
        self.version_name.setPlaceholderText("Eg: 'vga', 'en', '1.2', ...")
        layout.addWidget(self.version_label)
        layout.addWidget(self.version_name)
        self.setLayout(layout)

        self.registerField("game.version", self.version_name)


class ExecutablePage(QWizardPage):
    def __init__(self, game_archive: str, parent=None):
        super().__init__(parent)
        self.setTitle("Game executable")
        self.setSubTitle("Pick the executable file to start the game")

        layout = QVBoxLayout(self)
        self.binary_list_view = QListView(self)
        self.binary_list_model = BinaryListModel()
        self.binary_list_view.setModel(self.binary_list_model)
        self.binary_list_view.setSelectionMode(QListView.SingleSelection)
        self.selected_binary = None
        self.binary_list_view.selectionModel().selectionChanged.connect(self.completeChanged)
        layout.addWidget(self.binary_list_view)
        self.populates_binary_list(game_archive, self.binary_list_model)

        self.setLayout(layout)

    def isComplete(self):
        return len(self.binary_list_view.selectedIndexes()) == 1

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


class ConfigPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)


class CPUPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)


class DosBoxOptions(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
