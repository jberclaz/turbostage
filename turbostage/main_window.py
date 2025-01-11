import os
import sqlite3
import subprocess
import tempfile
import zipfile

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from turbostage import utils
from turbostage.igdb import Igdb
from turbostage.utils import find_game_for_hashes


class ScanningThread(QThread):
    progress = Signal(int)

    def __init__(self, local_game_archives: list[str], main_window):
        super().__init__()
        self._local_game_archives = local_game_archives
        self._main_window = main_window

    def run(self):
        conn = sqlite3.connect(MainWindow.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM local_versions")

        for index, game_archive in enumerate(self._local_game_archives):
            hashes = utils.compute_hash_for_largest_files_in_zip(os.path.join(MainWindow.GAMES_PATH, game_archive), 4)
            version_id = find_game_for_hashes([h[2] for h in hashes], MainWindow.DB_PATH)
            if version_id is not None:
                cursor.execute(
                    "INSERT INTO local_versions (version_id, archive) VALUES (?, ?)", (version_id, game_archive)
                )
            self.progress.emit(index + 1)

        conn.commit()
        conn.close()

        self._main_window.load_games()


class MainWindow(QMainWindow):
    DB_PATH = "db/games.db"
    GAMES_PATH = "games"
    DOSBOX_EXEC = "/home/jrb/downloads/dosbox-staging-linux-x86_64-0.82.0-9df43/dosbox"

    def __init__(self):
        QMainWindow.__init__(self)
        self._init_ui()
        self.load_games()
        self._igdb_client = Igdb()

    def _init_ui(self):
        self.setWindowTitle("TurboStage")

        # Menu
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        # Exit QAction
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)

        # Scan QAction
        scan_action = QAction("Scan local games", self)
        scan_action.triggered.connect(self.scan_local_games)

        # Add new game
        add_action = QAction("Add new game", self)
        add_action.triggered.connect(self.add_new_game)

        # Settings
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.settings_dialog)

        self.file_menu.addAction(add_action)
        self.file_menu.addAction(scan_action)
        self.file_menu.addAction(settings_action)
        self.file_menu.addSeparator()
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
        self.game_table.setColumnCount(4)
        self.game_table.setHorizontalHeaderLabels(["Title", "Release Year", "Genre", "Version"])
        self.game_table.setSortingEnabled(True)
        self.game_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.game_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.game_table.selectionModel().selectionChanged.connect(self.update_game_info)
        self.game_table.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        self.game_table.cellDoubleClicked.connect(self.launch_game)
        self.game_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
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
        cursor.execute(
            """
            SELECT v.executable, lv.archive, v.config
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id
            WHERE g.title = ?
            """,
            (game_name,),
        )
        rows = cursor.fetchall()
        conn.close()

        startup, archive, config = rows[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(self.GAMES_PATH, archive)
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            dosbox_command = os.path.join(temp_dir, startup)
            command = [self.DOSBOX_EXEC, "--noprimaryconf", "--conf", "conf/dosbox-staging.conf"]
            with tempfile.NamedTemporaryFile() as conf_file:
                if config:
                    with open(conf_file.name, "wt") as f:
                        f.write(config)
                    command.extend(["--conf", conf_file.name])
                command.append(dosbox_command)
                subprocess.run(command)

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
        cursor.execute(
            """
            SELECT g.title, g.release_year, g.genre, v.version
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id;
            """
        )
        rows = cursor.fetchall()
        conn.close()

        self.game_table.setRowCount(len(rows))
        for row_num, row in enumerate(rows):
            self.game_table.setItem(row_num, 0, QTableWidgetItem(row[0]))
            self.game_table.setItem(row_num, 1, QTableWidgetItem(str(row[1])))
            self.game_table.setItem(row_num, 2, QTableWidgetItem(row[2]))
            self.game_table.setItem(row_num, 3, QTableWidgetItem(row[3]))
        self.game_table.resizeColumnsToContents()

    def scan_local_games(self):
        local_game_archives = [file for file in os.listdir(MainWindow.GAMES_PATH) if file.endswith(".zip")]

        self.scan_progress_dialog = QProgressDialog(
            "Scanning local games...", "Cancel", 0, len(local_game_archives), self
        )
        self.scan_progress_dialog.setWindowTitle("Please Wait")
        self.scan_progress_dialog.setWindowModality(Qt.WindowModal)
        self.scan_progress_dialog.setMinimumDuration(0)
        self.scan_progress_dialog.setValue(0)

        # Start the worker thread
        self.scan_worker = ScanningThread(local_game_archives, self)
        self.scan_worker.progress.connect(self.update_scan_progress)
        self.scan_worker.start()

        # Handle cancellation
        self.scan_progress_dialog.canceled.connect(self.cancel_scan)

    def update_scan_progress(self, value):
        self.scan_progress_dialog.setValue(value)

    def cancel_scan(self):
        if self.scan_worker.isRunning():
            self.scan_worker.terminate()  # Forcefully stop the worker thread
        self.scan_progress_dialog.close()

    def add_new_game(self):
        pass

    def settings_dialog(self):
        pass