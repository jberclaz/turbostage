import importlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import requests
from PySide6 import QtWidgets
from PySide6.QtCore import QSettings, QStandardPaths, Qt, QThreadPool
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from turbostage import __version__, constants, utils
from turbostage.add_game_worker import AddGameWorker
from turbostage.db.populate_db import initialize_database
from turbostage.fetch_game_info_thread import FetchGameInfoTask, FetchGameInfoWorker
from turbostage.game_database import GameDatabase
from turbostage.game_launcher import GameLauncher
from turbostage.igdb_client import IgdbClient
from turbostage.scanning_thread import ScanningThread
from turbostage.ui.add_new_game_dialog import AddNewGameDialog
from turbostage.ui.configure_game_dialog import ConfigureGameDialog
from turbostage.ui.game_info_widget import GameInfoWidget
from turbostage.ui.game_setup_dialog import GameSetupDialog
from turbostage.ui.game_setup_widget import GameSetupWidget
from turbostage.ui.settings_dialog import SettingsDialog


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
        self._gamedb = GameDatabase(self.db_path)

        self._init_ui()
        self.load_games()

    def _init_ui(self):
        self.setWindowTitle(f"TurboStage {__version__}")
        with importlib.resources.files("turbostage").joinpath("content/icon.png") as image:
            icon = QIcon(str(image))
            self.setWindowIcon(icon)

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
        add_action.triggered.connect(self._on_add_new_game)

        # Update game database
        update_db_action = QAction("Update game database", self)
        update_db_action.triggered.connect(self._on_update_game_database)

        # Settings
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._on_show_settings_dialog)

        self.file_menu.addAction(add_action)
        self.file_menu.addAction(scan_action)
        self.file_menu.addAction(update_db_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(settings_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(exit_action)

        # Status Bar
        self.status = self.statusBar()

        # Window dimensions
        geometry = self.screen().availableGeometry()
        self.setGeometry(geometry.width() // 4, geometry.height() // 4, geometry.width() // 2, geometry.height() // 2)
        self.setMinimumSize(800, 600)

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Search for a game...")
        self.search_box.textChanged.connect(self.filter_games)

        self.splitter = QSplitter(Qt.Horizontal)

        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout()

        # Game table
        self.game_table = QTableWidget()
        self.game_table.setColumnCount(4)
        self.game_table.setHorizontalHeaderLabels(["Title", "Release", "Genre", "Version"])
        self.game_table.setSortingEnabled(True)
        self.game_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.game_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.game_table.selectionModel().selectionChanged.connect(self.on_game_change)
        self.game_table.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        self.game_table.cellDoubleClicked.connect(self.launch_game)
        self.game_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_table.customContextMenuRequested.connect(self._on_show_context_menu)
        self.game_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.left_layout.addWidget(self.search_box)
        self.left_layout.addWidget(self.game_table)
        self.left_panel.setLayout(self.left_layout)
        self.splitter.addWidget(self.left_panel)

        # Right panel: Game info display
        self.right_panel = QTabWidget()
        self.right_info_tab = GameInfoWidget()
        self.right_setup_tab = GameSetupWidget()
        self.right_setup_tab.settings_applied.connect(self._on_game_settings_saved)
        self.right_panel.addTab(self.right_info_tab, "Info")
        self.right_panel.addTab(self.right_setup_tab, "Setup")
        self.splitter.addWidget(self.right_panel)

        # Launch button
        self.launch_button = QPushButton("Launch Game")
        self.launch_button.clicked.connect(self.launch_game)
        self.launch_button.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.splitter)
        layout.addWidget(self.launch_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.scan_progress_dialog = None

    def filter_games(self, query: str):
        for row in range(self.game_table.rowCount()):
            title = self.game_table.item(row, 0)
            match = title and (query.lower() in title.text().lower())
            self.game_table.setRowHidden(row, not match)

    def launch_game(self):
        game_id, _ = self.selected_game
        gl = GameLauncher(track_change=True)
        gl.launch_game(game_id, self.db_path)
        if gl.new_files or gl.modified_files:
            config_files = {**gl.new_files, **gl.modified_files}
            utils.add_extra_files(config_files, gl.version_id, constants.FileType.SAVEGAME, self.db_path)

    def on_game_change(self):
        selected_items = self.game_table.selectedItems()
        if not selected_items:
            self.right_info_tab.set_game_name("")
            self.right_setup_tab.set_game(None)
            self.launch_button.setEnabled(False)
            return
        if len(selected_items) != 4:
            raise RuntimeError("Invalid game selection")
        if self._current_fetch_cancel_flag is not None:
            self._current_fetch_cancel_flag.cancelled = True

        name_row = selected_items[0]
        game_id = name_row.data(Qt.UserRole)
        game_name = name_row.text()

        self.right_info_tab.set_game_name(game_name)
        self.right_setup_tab.set_game(game_id, self.db_path)

        settings = QSettings("jberclaz", "TurboStage")
        dosbox_exec = str(settings.value("app/emulator_path", ""))
        self.launch_button.setEnabled(dosbox_exec != "")

        cancel_flag = utils.CancellationFlag()
        fetch_worker = FetchGameInfoWorker(game_id, self._igdb_client, self.db_path, cancel_flag)
        self._current_fetch_cancel_flag = cancel_flag
        fetch_worker.finished.connect(self.right_info_tab.set_game_info)
        fetch_task = FetchGameInfoTask(fetch_worker)
        self._thread_pool.start(fetch_task)

    def load_games(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT g.title, g.release_date, g.genre, v.version, g.igdb_id
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id;
            """
        )
        rows = cursor.fetchall()
        conn.close()

        self.game_table.setSortingEnabled(False)
        self.game_table.setRowCount(len(rows))
        for row_num, row in enumerate(rows):
            game_name = QTableWidgetItem(row[0])
            game_name.setData(Qt.UserRole, row[4])
            dt_object = datetime.fromtimestamp(row[1], timezone.utc)
            release_date = dt_object.strftime("%Y-%m-%d")

            self.game_table.setItem(row_num, 0, game_name)
            self.game_table.setItem(row_num, 1, QTableWidgetItem(release_date))
            self.game_table.setItem(row_num, 2, QTableWidgetItem(row[2]))
            self.game_table.setItem(row_num, 3, QTableWidgetItem(row[3]))
        self.game_table.resizeColumnsToContents()
        self.game_table.setSortingEnabled(True)

    def scan_local_games(self):
        games_path = self.games_path
        if not games_path:
            QMessageBox.critical(
                self,
                "Games folder not specified",
                "Cannot scan local games, because the games folder has not been specified. Use the Settings dialog to set it up.",
                QMessageBox.Ok,
            )
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
        self.scan_progress_dialog.canceled.connect(self._on_cancel_scan)

    def update_scan_progress(self, value):
        self.scan_progress_dialog.setValue(value)

    def _on_cancel_scan(self):
        if self.scan_worker.isRunning():
            self.scan_worker.terminate()  # Forcefully stop the worker thread
        self.scan_progress_dialog.close()

    def _on_add_new_game(self):
        games_path = self.games_path
        game_path, _ = QFileDialog.getOpenFileName(self, "Select game archive", games_path, "Game archives (*.zip)")
        if not game_path:
            return
        hashes = utils.compute_hash_for_largest_files_in_zip(game_path, 4)
        version_id = utils.find_game_for_hashes([h[2] for h in hashes], self.db_path)
        if version_id is not None:
            QMessageBox.warning(
                self,
                "Game already in database",
                "It looks like this game is already known from the game database. To add it, simply run Scan Local Games option from the main menu.",
            )
            return
        new_game_dialog = AddNewGameDialog(self._igdb_client, os.path.basename(game_path), self)
        if new_game_dialog.exec() != QDialog.Accepted:
            return
        game_name, game_id = new_game_dialog.selected_game
        configure_dialog = ConfigureGameDialog(game_path)
        if configure_dialog.exec() != QDialog.Accepted:
            return
        binary = configure_dialog.selected_binary
        version = configure_dialog.version
        cycles = configure_dialog.cpu_cycles
        config = configure_dialog.config_text

        add_game_worker = AddGameWorker(
            game_name, version, game_id, game_path, binary, cycles, config, self.db_path, self._igdb_client
        )
        add_game_worker.signals.task_finished.connect(self._on_game_added)
        self._thread_pool.start(add_game_worker)
        self.status.showMessage("Adding new game...", 3000)
        QGuiApplication.setOverrideCursor(Qt.BusyCursor)

    def _on_game_added(self):
        self.load_games()
        QGuiApplication.restoreOverrideCursor()  # Restore normal cursor
        self.status.showMessage("New game added.", 3000)

    def _on_show_settings_dialog(self):
        dialog = SettingsDialog()
        dialog.exec()

    def _on_update_game_database(self):
        version = self._gamedb.get_version()

        response = requests.get(self.ONLINE_DB_VERSION_URL)
        if response.status_code != 200:
            QMessageBox.critical(
                self,
                "Online database unavailable",
                "Unable to access online database. Please retry in a few minutes.",
                QMessageBox.Ok,
            )
            return

        online_version = json.loads(response.content)["version"]

        if version > online_version:
            QMessageBox.warning(
                self,
                "Database NOT updated",
                "The game database was not updated because the online version is too old.",
                QMessageBox.Ok,
            )
            return
        if version < online_version:
            QMessageBox.warning(
                self,
                "Database NOT updated",
                "The game database was not updated because the online version is too old. Please upgrade TurboStage to the latest version.",
                QMessageBox.Ok,
            )
            return

        response = requests.get(self.ONLINE_DB_URL)
        if response.status_code != 200:
            QMessageBox.critical(
                self,
                "Online database unavailable",
                "Unable to access online database. Please retry in a few minutes.",
                QMessageBox.Ok,
            )
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(response.content)
            error = self._gamedb.merge_with(temp_file.name)
            if error:
                QMessageBox.warning(self, "Could not update database", error, QMessageBox.Ok)

        QMessageBox.information(
            self, "Database updated", "The game database has been updated to the latest version.", QMessageBox.Ok
        )

    def _on_show_context_menu(self, pos):
        context_menu = QMenu(self)

        setup_action = QAction("Run Game Setup", self)
        setup_action.triggered.connect(self._on_run_game_setup)
        context_menu.addAction(setup_action)

        delete_action = QAction("Delete Game", self)
        delete_action.triggered.connect(self._on_delete_selected_game)
        context_menu.addAction(delete_action)

        context_menu.exec(self.game_table.mapToGlobal(pos))

    def _on_delete_selected_game(self):
        game_id, game_name = self.selected_game

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to remove '{game_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            utils.delete_local_game(game_id, self.db_path)
            self.load_games()

    def _on_run_game_setup(self):
        game_id, _ = self.selected_game
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT lv.archive, v.id
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id
            WHERE g.igdb_id = ?
            """,
            (game_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        settings = QSettings("jberclaz", "TurboStage")
        games_path = str(settings.value("app/games_path", ""))

        game_archive, version_id = rows[0]
        game_archive_url = os.path.join(games_path, game_archive)
        setup_dialog = GameSetupDialog(game_archive_url)
        if setup_dialog.exec() != QDialog.Accepted:
            return
        gl = GameLauncher(track_change=True)
        gl.launch_game(game_id, self.db_path, False, False, setup_dialog.selected_binary)
        if gl.new_files or gl.modified_files:
            config_files = {**gl.new_files, **gl.modified_files}
            utils.add_extra_files(config_files, version_id, constants.FileType.CONFIG, self.db_path)

    def _on_game_settings_saved(self):
        version_id = self.right_setup_tab.version_id
        binary = self.right_setup_tab.selected_binary
        config = self.right_setup_tab.dosbox_config_text.toPlainText()
        cycles = self.right_setup_tab.cpu_cycles
        utils.update_version_info(version_id, None, binary, config, cycles, self.db_path)

    @property
    def db_path(self):
        p = os.path.join(self._app_data_folder, self.DB_FILE)
        if not os.path.isfile(p):
            initialize_database(p)
        return p

    @property
    def games_path(self) -> str:
        settings = QSettings("jberclaz", "TurboStage")
        return str(settings.value("app/games_path", ""))

    @property
    def selected_game(self) -> tuple[int, str]:
        selected_items = self.game_table.selectedItems()
        if len(selected_items) != 4:
            raise RuntimeError("Invalid game selection")
        name_row = selected_items[0]
        game_id = name_row.data(Qt.UserRole)
        game_name = name_row.text()
        return game_id, game_name
