import os
import sqlite3
import subprocess
import tempfile
import zipfile

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    DB_PATH = "db/games.db"
    GAMES_PATH = "games"
    DOSBOX_EXEC = "/home/jrb/downloads/dosbox-staging-linux-x86_64-0.82.0-9df43/dosbox"

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

        main_layout = QHBoxLayout()

        # Game table
        self.game_table = QTableWidget()
        self.game_table.setColumnCount(3)
        self.game_table.setHorizontalHeaderLabels(["Title", "Release Year", "Genre"])
        self.game_table.setSortingEnabled(True)
        self.game_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.game_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.game_table.selectionModel().selectionChanged.connect(self.update_game_info)
        self.game_table.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        main_layout.addWidget(self.game_table)

        # Right panel: Game info display
        self.game_panel = QVBoxLayout()
        self.game_info_label = QLabel("Select a game to see details here.")
        self.game_info_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.game_panel.addWidget(self.game_info_label)
        main_layout.addLayout(self.game_panel)

        # Launch button
        self.launch_button = QPushButton("Launch Game")
        self.launch_button.clicked.connect(self.launch_game)
        self.launch_button.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.search_box)
        layout.addLayout(main_layout)
        layout.addWidget(self.launch_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def filter_games(self):
        pass

    def launch_game(self):
        selected_row = self.game_table.currentRow()
        game_name = self.game_table.item(selected_row, 0).text()

        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT config, archive FROM games WHERE title = ?", (game_name,))
        rows = cursor.fetchall()
        conn.close()

        config, archive = rows[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(self.GAMES_PATH, archive)
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            command = os.path.join(temp_dir, config)
            subprocess.run([self.DOSBOX_EXEC, command])

    def update_game_info(self):
        selected_items = self.game_table.selectedItems()
        if not selected_items:
            self.game_info_label.setText("Select a game to see details here.")
            self.launch_button.setEnabled(False)
            return
        selected_row = self.game_table.currentRow()
        game_name = self.game_table.item(selected_row, 0).text()
        self.game_info_label.setText(f"{game_name}")
        self.launch_button.setEnabled(True)

    def load_games(self):
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT title, release_year, genre FROM games ORDER BY title ASC")
        rows = cursor.fetchall()
        conn.close()

        self.game_table.setRowCount(len(rows))
        for row_num, row in enumerate(rows):
            self.game_table.setItem(row_num, 0, QTableWidgetItem(row[0]))
            self.game_table.setItem(row_num, 1, QTableWidgetItem(str(row[1])))
            self.game_table.setItem(row_num, 2, QTableWidgetItem(row[2]))
        self.game_table.resizeColumnsToContents()
