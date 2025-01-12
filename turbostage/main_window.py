import json
import os
import sqlite3
import subprocess
import tempfile
import zipfile

import requests
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QThreadPool, QSettings, QStandardPaths
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget, QMessageBox, QFileDialog, QDialog,
)

from turbostage.add_new_game_dialog import AddNewGameDialog
from turbostage.configure_game_dialog import ConfigureGameDialog
from turbostage.db.populate_db import initialize_database
from turbostage.fetch_game_info_thread import FetchGameInfoTask, FetchGameInfoWorker
from turbostage.game_info_widget import GameInfoWidget
from turbostage.igdb_client import IgdbClient
from turbostage.scanning_thread import ScanningThread
from turbostage.settings_dialog import SettingsDialog
from turbostage import utils, __version__


class MainWindow(QMainWindow):
    DB_FILE = "turbostage.db"
    ONLINE_DB_URL = "https://github.com/jberclaz/turbostage_data/raw/refs/heads/master/turbostage.db"
    ONLINE_DB_VERSION_URL = "https://raw.githubusercontent.com/jberclaz/turbostage_data/refs/heads/master/version.json"

    def __init__(self):
        QMainWindow.__init__(self)
        self._igdb_client = IgdbClient()
        self._current_fetch_cancel_flag = None
        self._thread_pool = QThreadPool()
        self._app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))

        self._init_ui()
        self.load_games()

    def _init_ui(self):
        self.setWindowTitle(f"TurboStage {__version__}")

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

        # Update game database
        update_db_action = QAction("Update game database", self)
        update_db_action.triggered.connect(self.update_game_database)

        # Settings
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.settings_dialog)

        self.file_menu.addAction(add_action)
        self.file_menu.addAction(scan_action)
        self.file_menu.addAction(update_db_action)
        self.file_menu.addSeparator()
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
        self.game_info_panel = GameInfoWidget()
        main_layout.addWidget(self.game_info_panel)

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

        conn = sqlite3.connect(self.db_path)
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

        settings = QSettings("jberclaz", "TurboStage")
        full_screen = settings.value("app/full_screen", False)
        dosbox_exec = settings.value("app/emulator_path", "")
        games_path = settings.value("app/games_path", "")
        if not dosbox_exec:
            QMessageBox.critical(self, "DosBox binary not specified", "Cannot start game, because the DosBox Staging binary has not been specified. Use the Settings dialog to set it up or download DosBox Staging", QMessageBox.Ok)
            return

        startup, archive, config = rows[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(games_path, archive)
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            dosbox_command = os.path.join(temp_dir, startup)
            command = [dosbox_exec, "--noprimaryconf", "--conf", "conf/dosbox-staging.conf"]
            if full_screen:
                command.append("--fullscreen")
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
        if len(selected_items) != 4:
            raise RuntimeError("Invalid game selection")
        if self._current_fetch_cancel_flag is not None:
            self._current_fetch_cancel_flag.cancelled = True

        name_row = selected_items[0]
        game_id = name_row.data(Qt.UserRole)
        game_name = name_row.text()
        self.game_info_panel.set_game_name(game_name)
        self.launch_button.setEnabled(True)
        cancel_flag = utils.CancellationFlag()
        fetch_worker = FetchGameInfoWorker(game_id, self._igdb_client, cancel_flag)
        self._current_fetch_cancel_flag = cancel_flag
        fetch_worker.finished.connect(self.game_info_panel.set_game_info)
        fetch_task = FetchGameInfoTask(fetch_worker)
        self._thread_pool.start(fetch_task)

    def load_games(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT g.title, g.release_year, g.genre, v.version, g.igdb_id
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id;
            """
        )
        rows = cursor.fetchall()
        conn.close()

        self.game_table.setRowCount(len(rows))
        for row_num, row in enumerate(rows):
            game_name = QTableWidgetItem(row[0])
            game_name.setData(Qt.UserRole, row[4])
            self.game_table.setItem(row_num, 0, game_name)
            self.game_table.setItem(row_num, 1, QTableWidgetItem(str(row[1])))
            self.game_table.setItem(row_num, 2, QTableWidgetItem(row[2]))
            self.game_table.setItem(row_num, 3, QTableWidgetItem(row[3]))
        self.game_table.resizeColumnsToContents()

    def scan_local_games(self):
        settings = QSettings("jberclaz", "TurboStage")
        games_path = settings.value("app/games_path", "")
        if not games_path:
            QMessageBox.critical(self, "Games folder not specified", "Cannot scan local games, because the games folder has not been specified. Use the Settings dialog to set it up.", QMessageBox.Ok)
            return
        local_game_archives = [file for file in os.listdir(games_path) if file.endswith(".zip")]

        self.scan_progress_dialog = QProgressDialog(
            "Scanning local games...", "Cancel", 0, len(local_game_archives), self
        )
        self.scan_progress_dialog.setWindowTitle("Please Wait")
        self.scan_progress_dialog.setWindowModality(Qt.WindowModal)
        self.scan_progress_dialog.setMinimumDuration(0)
        self.scan_progress_dialog.setValue(0)

        # Start the worker thread
        self.scan_worker = ScanningThread(local_game_archives, self.db_path, games_path)
        self.scan_worker.progress.connect(self.update_scan_progress)
        self.scan_worker.load_games.connect(self.load_games)
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
        settings = QSettings("jberclaz", "TurboStage")
        games_path = settings.value("app/games_path", "")
        game_path, _ = QFileDialog.getOpenFileName(self, "Select DosBox Staging binary", games_path, "Game archives (*.zip)")
        hashes = utils.compute_hash_for_largest_files_in_zip(game_path, 4)
        version_id = utils.find_game_for_hashes([h[2] for h in hashes], self.db_path)
        if version_id is not None:
            QMessageBox.warning(self, "Game already in database", "It looks like this game is already known from the game database. To add it, simply run Scan Local Games option from the main menu.")
            return
        new_game_dialog = AddNewGameDialog(self._igdb_client)
        if new_game_dialog.exec() != QDialog.Accepted:
            return
        game_name, game_id = new_game_dialog.selected_game
        configure_dialog = ConfigureGameDialog(game_name, game_id)
        if configure_dialog.exec() != QDialog.Accepted:
            return

    def settings_dialog(self):
        dialog = SettingsDialog()
        dialog.exec()

    def update_game_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM db_version")
        rows = cursor.fetchall()
        conn.close()
        version = rows[0][0]

        response = requests.get(self.ONLINE_DB_VERSION_URL)
        if response.status_code != 200:
            QMessageBox.critical(self, "Online database unavailable", "Unable to access online database. Please retry in a few minutes.", QMessageBox.Ok)
            return

        online_version = json.loads(response.content)["version"]

        # TODO: properly compare versions

        if version == online_version:
            QMessageBox.information(self, "Database up to date",
                                 "The game database is already up to date.", QMessageBox.Ok)
            return

        response = requests.get(self.ONLINE_DB_URL)
        if response.status_code != 200:
            QMessageBox.critical(self, "Online database unavailable",
                                 "Unable to access online database. Please retry in a few minutes.", QMessageBox.Ok)
        with open(self.db_path, "wb") as database_file:
            database_file.write(response.content)
        QMessageBox.information(self, "Database updated",
                                "The game database has been updated to the latest version.", QMessageBox.Ok)

    @property
    def db_path(self):
        p = os.path.join(self._app_data_folder, self.DB_FILE)
        if not os.path.isfile(p):
            initialize_database(p)
        return p