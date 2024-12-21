import sqlite3

from PySide6.QtGui import QAction, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLineEdit, QListView, QMainWindow, QPushButton, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    DB_PATH = "db/games.db"

    def __init__(self):
        QMainWindow.__init__(self)
        self._init_ui()
        self.load_games()

    def _init_ui(self):
        self.setWindowTitle("TurboStage")

        # Menu
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        # Exit QAction
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)

        self.file_menu.addAction(exit_action)

        # Status Bar
        self.status = self.statusBar()
        self.status.showMessage("Status bar")

        # Window dimensions
        geometry = self.screen().availableGeometry()
        self.setGeometry(geometry.width() / 4, geometry.height() / 4, geometry.width() * 0.5, geometry.height() * 0.5)
        self.setMinimumSize(800, 600)

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Search for a game...")
        self.search_box.textChanged.connect(self.filter_games)

        self.game_list = QListView(self)
        self.model = QStandardItemModel(self.game_list)
        self.game_list.setModel(self.model)

        # Launch button
        self.launch_button = QPushButton("Launch Game")
        self.launch_button.clicked.connect(self.launch_game)

        layout = QVBoxLayout()
        layout.addWidget(self.search_box)
        layout.addWidget(self.game_list)
        layout.addWidget(self.launch_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def filter_games(self):
        pass

    def launch_game(self):
        pass

    def load_games(self):
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT title, release_year, genre FROM games ORDER BY title ASC")
        rows = cursor.fetchall()
        conn.close()

        self.model.clear()
        for title, year, genre in rows:
            item = QStandardItem(f"{title} ({year}) - {genre}")
            item.setData({"title": title, "release_year": year, "genre": genre})
            self.model.appendRow(item)
