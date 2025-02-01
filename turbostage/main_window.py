import importlib
import json
import os
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone

import requests
from PySide6 import QtWidgets
from PySide6.QtCore import QSettings, QStandardPaths, Qt, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
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
    QVBoxLayout,
    QWidget,
)

from turbostage import __version__, utils
from turbostage.add_new_game_dialog import AddNewGameDialog
from turbostage.configure_game_dialog import ConfigureGameDialog
from turbostage.db.populate_db import initialize_database
from turbostage.fetch_game_info_thread import FetchGameInfoTask, FetchGameInfoWorker
from turbostage.game_info_widget import GameInfoWidget
from turbostage.game_setup_dialog import GameSetupDialog
from turbostage.igdb_client import IgdbClient
from turbostage.scanning_thread import ScanningThread
from turbostage.settings_dialog import SettingsDialog


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
        self.setGeometry(geometry.width() // 4, geometry.height() // 4, geometry.width() // 2, geometry.height() // 2)
        self.setMinimumSize(800, 600)

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Search for a game...")
        self.search_box.textChanged.connect(self.filter_games)

        self.splitter = QSplitter(Qt.Horizontal)

        # Game table
        self.game_table = QTableWidget()
        self.game_table.setColumnCount(4)
        self.game_table.setHorizontalHeaderLabels(["Title", "Release", "Genre", "Version"])
        self.game_table.setSortingEnabled(True)
        self.game_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.game_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.game_table.selectionModel().selectionChanged.connect(self.update_game_info)
        self.game_table.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        self.game_table.cellDoubleClicked.connect(self.launch_game)
        self.game_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_table.customContextMenuRequested.connect(self.show_context_menu)
        self.game_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.splitter.addWidget(self.game_table)

        # Right panel: Game info display
        self.game_info_panel = GameInfoWidget()
        self.splitter.addWidget(self.game_info_panel)

        # Launch button
        self.launch_button = QPushButton("Launch Game")
        self.launch_button.clicked.connect(self.launch_game)
        self.launch_button.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.search_box)
        layout.addWidget(self.splitter)
        layout.addWidget(self.launch_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.scan_progress_dialog = None

    def filter_games(self):
        pass

    def launch_game(self):
        game_id, _ = self.selected_game
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT v.executable, lv.archive, v.config, v.cycles, v.id
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
        full_screen = utils.to_bool(settings.value("app/full_screen", False))
        dosbox_exec = str(settings.value("app/emulator_path", ""))
        games_path = str(settings.value("app/games_path", ""))
        mt32_roms_path = str(settings.value("app/mt32_path", ""))
        if not dosbox_exec:
            QMessageBox.critical(
                self,
                "DosBox binary not specified",
                "Cannot start game, because the DosBox Staging binary has not been specified. Use the Settings dialog to set it up or download DosBox Staging",
                QMessageBox.Ok,
            )
            return

        startup, archive, config, cpu_cycles, version_id = rows[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(games_path, archive)
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
            SELECT path, content FROM config_files
            WHERE version_id = ?
            """,
                (version_id,),
            )
            rows = cursor.fetchall()
            conn.close()
            for config_file_path, content in rows:
                with open(os.path.join(temp_dir, config_file_path), "wb") as f:
                    f.write(content)

            dosbox_command = os.path.join(temp_dir, startup)
            main_config = importlib.resources.files("turbostage").joinpath("conf/dosbox-staging.conf")
            command = [dosbox_exec, "--noprimaryconf", "--conf", str(main_config)]
            if full_screen:
                command.append("--fullscreen")
            with tempfile.NamedTemporaryFile() as conf_file:
                if config or mt32_roms_path:
                    with open(conf_file.name, "wt") as f:
                        if config:
                            f.write(config)
                        if cpu_cycles > 0:
                            f.write(f"\n[cpu]\ncpu_cycles = {cpu_cycles}\n")
                        if mt32_roms_path:
                            f.write(f"\n[mt32]\nromdir = {mt32_roms_path}\n")
                    command.extend(["--conf", conf_file.name])
                command.append(dosbox_command)
                subprocess.run(command)

    def update_game_info(self):
        selected_items = self.game_table.selectedItems()
        if not selected_items:
            self.game_info_panel.set_game_name("")
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
        fetch_worker = FetchGameInfoWorker(game_id, self._igdb_client, self.db_path, cancel_flag)
        self._current_fetch_cancel_flag = cancel_flag
        fetch_worker.finished.connect(self.game_info_panel.set_game_info)
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
        self.scan_progress_dialog.canceled.connect(self.cancel_scan)

    def update_scan_progress(self, value):
        self.scan_progress_dialog.setValue(value)

    def cancel_scan(self):
        if self.scan_worker.isRunning():
            self.scan_worker.terminate()  # Forcefully stop the worker thread
        self.scan_progress_dialog.close()

    def add_new_game(self):
        games_path = self.games_path
        game_path, _ = QFileDialog.getOpenFileName(
            self, "Select DosBox Staging binary", games_path, "Game archives (*.zip)"
        )
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
        new_game_dialog = AddNewGameDialog(self._igdb_client, self)
        if new_game_dialog.exec() != QDialog.Accepted:
            return
        game_name, game_id = new_game_dialog.selected_game
        configure_dialog = ConfigureGameDialog(game_name, game_id, game_path)
        if configure_dialog.exec() != QDialog.Accepted:
            return
        binary = configure_dialog.selected_binary
        version = configure_dialog.version_name.text()
        cycles = configure_dialog.cpu_cycles
        config = configure_dialog.dosbox_config_text.toPlainText()
        try:
            utils.add_new_game_version(
                game_name, version, game_id, game_path, binary, cycles, config, self.db_path, self._igdb_client
            )
        except RuntimeError as e:
            QMessageBox.critical("Error", "Unable to add new game", str(e))
            return
        self.load_games()

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
            QMessageBox.critical(
                self,
                "Online database unavailable",
                "Unable to access online database. Please retry in a few minutes.",
                QMessageBox.Ok,
            )
            return

        online_version = json.loads(response.content)["version"]

        # TODO: properly compare versions

        if version == online_version:
            QMessageBox.information(
                self, "Database up to date", "The game database is already up to date.", QMessageBox.Ok
            )
            return
        else:
            online_major, online_minor, online_patch = map(int, online_version.split("."))
            major, minor, patch = map(int, version.split("."))
            if online_major != major:
                upgrade_ok = online_major > major
            elif online_minor != minor:
                upgrade_ok = online_minor > minor
            else:
                upgrade_ok = online_patch > patch
            if not upgrade_ok:
                QMessageBox.warning(
                    self,
                    "Database NOT updated",
                    "The game database was not updated because the online version is too old.",
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
        with open(self.db_path, "wb") as database_file:
            database_file.write(response.content)
        QMessageBox.information(
            self, "Database updated", "The game database has been updated to the latest version.", QMessageBox.Ok
        )

    def show_context_menu(self, pos):
        context_menu = QMenu(self)

        edit_action = QAction("Edit Game", self)
        edit_action.triggered.connect(self.edit_selected_game)
        context_menu.addAction(edit_action)

        setup_action = QAction("Run Game Setup", self)
        setup_action.triggered.connect(self.run_game_setup)
        context_menu.addAction(setup_action)

        delete_action = QAction("Delete Game", self)
        delete_action.triggered.connect(self.delete_selected_game)
        context_menu.addAction(delete_action)

        context_menu.exec(self.game_table.mapToGlobal(pos))

    def delete_selected_game(self):
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

    def edit_selected_game(self):
        game_id, game_name = self.selected_game

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT v.executable, lv.archive, v.config, v.cycles, v.version, v.id
            FROM games g
            JOIN versions v ON g.id = v.game_id
            JOIN local_versions lv ON v.id = lv.version_id
            WHERE g.igdb_id = ?
            """,
            (game_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        if len(rows) != 1:
            raise RuntimeError(f"Unable to get game details for '{game_name}'")
        game_details = rows[0]
        game_binary, game_archive, game_config, cpu_cycles, game_version, version_id = game_details

        games_path = self.games_path
        game_path = os.path.join(games_path, game_archive)

        configure_dialog = ConfigureGameDialog(
            game_name,
            game_id,
            game_path,
            version=game_version,
            binary=game_binary,
            cycles=cpu_cycles,
            config=game_config,
            add=False,
        )
        if configure_dialog.exec() == QDialog.Accepted:
            binary = configure_dialog.selected_binary
            version = configure_dialog.version_name.text()
            config = configure_dialog.dosbox_config_text.toPlainText()
            cycles = configure_dialog.cpu_cycles
            utils.update_version_info(version_id, version, binary, config, cycles, self.db_path)

    def run_game_setup(self):
        game_id, game_name = self.selected_game
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT lv.archive, v.config, v.id
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
        dosbox_exec = str(settings.value("app/emulator_path", ""))
        games_path = str(settings.value("app/games_path", ""))
        mt32_roms_path = str(settings.value("app/mt32_path", ""))

        game_archive, game_config, version_id = rows[0]
        game_archive_url = os.path.join(games_path, game_archive)
        setup_dialog = GameSetupDialog(game_archive_url)
        if setup_dialog.exec() != QDialog.Accepted:
            return
        startup = setup_dialog.selected_binary

        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(game_archive_url, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            original_files = utils.list_files_with_md5(temp_dir)
            dosbox_command = os.path.join(temp_dir, startup)
            main_config = importlib.resources.files("turbostage").joinpath("conf/dosbox-staging.conf")
            command = [dosbox_exec, "--noprimaryconf", "--conf", str(main_config)]
            with tempfile.NamedTemporaryFile() as conf_file:
                if game_config or mt32_roms_path:
                    with open(conf_file.name, "wt") as f:
                        if game_config:
                            f.write(game_config)
                        if mt32_roms_path:
                            f.write(f"\n[mt32]\nromdir = {mt32_roms_path}\n")
                    command.extend(["--conf", conf_file.name])
                command.append(dosbox_command)
                subprocess.run(command)

            config_files = []
            files_after_setup = utils.list_files_with_md5(temp_dir)
            for file_after_setup, file_hash in files_after_setup.items():
                if not file_after_setup in original_files:
                    config_files.append(file_after_setup)
                else:
                    if original_files[file_after_setup] != file_hash:
                        config_files.append(file_after_setup)

            if config_files:
                utils.add_config_files(config_files, version_id, temp_dir, self.db_path)

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
