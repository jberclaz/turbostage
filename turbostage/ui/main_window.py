import gzip
import importlib
import json
import os
import tempfile
from datetime import datetime, timezone

import requests
from PySide6 import QtWidgets
from PySide6.QtCore import QSettings, QStandardPaths, Qt, QThreadPool
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QKeySequence
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
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from turbostage import __version__, constants, utils
from turbostage.add_game_worker import AddGameWorker
from turbostage.constants import CPU_CYCLES
from turbostage.db.database_manager import DatabaseManager
from turbostage.db.game_database import GameDatabase
from turbostage.db.remote_db import RemoteDB
from turbostage.fetch_game_info_thread import FetchGameInfoTask, FetchGameInfoWorker
from turbostage.game_launcher import GameLauncher
from turbostage.igdb_client import IgdbClient
from turbostage.scanning_thread import ScanningThread
from turbostage.ui.game_info_widget import GameInfoWidget
from turbostage.ui.game_setup_dialog import GameSetupDialog
from turbostage.ui.game_setup_widget import GameSetupWidget
from turbostage.ui.locked_file_dialog import LockedFileDialog
from turbostage.ui.new_game_wizard import NewGameWizard
from turbostage.ui.download_dialog import DownloaderDialog
from turbostage.ui.settings_dialog import SettingsDialog
from turbostage.ui.submit_config_dialog import SubmitLocalConfigDialog


class MainWindow(QMainWindow):
    DB_FILE = "turbostage.db"
    ONLINE_DB_URL = "https://github.com/jberclaz/turbostage_data/raw/refs/heads/master/archive/database.json.gz"

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
        icon = QIcon(str(importlib.resources.files("turbostage").joinpath("content/icon.png")))
        self.setWindowIcon(icon)

        # Menu
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        # Exit QAction
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setMenuRole(QAction.NoRole)
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

        # Update game database
        submit_local_config_action = QAction("Upload local config", self)
        submit_local_config_action.triggered.connect(self._on_submit_local_config)

        # Settings
        settings_action = QAction("Settings", self)
        settings_action.setMenuRole(QAction.NoRole)
        settings_action.triggered.connect(self._on_show_settings_dialog)

        self.file_menu.addAction(add_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(scan_action)
        self.file_menu.addAction(update_db_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(submit_local_config_action)
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
        self.right_info_tab = QScrollArea()
        self.right_info_tab.setWidgetResizable(True)
        # self.right_info_tab.setHorizontalScrollBarPolicy(Qt.ScrollBa)
        self._game_info = GameInfoWidget()
        self.right_info_tab.setWidget(self._game_info)
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
        # Check if we're in install mode
        needs_install = getattr(self, "_current_needs_install", False)
        version_id = getattr(self, "_current_version_id", None)
        is_downloadable = getattr(self, "_current_is_downloadable", False)

        if version_id is None:
            return

        # If this is a downloadable game, trigger download instead of launch
        if is_downloadable:
            self._on_download_game()
            return

        gl = GameLauncher(track_change=True)
        install_completed, install_path = gl.launch_game(version_id, self._gamedb, install_mode=needs_install)

        # If installation completed, prompt user to select game binary from installed files
        if install_completed and install_path:
            self._prompt_for_game_binary(version_id, install_path)

        # If we were in install mode and it succeeded, refresh the game list
        if needs_install or install_completed:
            self.load_games()
            self.on_game_change()  # Update button text
        elif gl.new_files or gl.modified_files:
            config_files = {**gl.new_files, **gl.modified_files}
            self._gamedb.add_extra_files(config_files, gl.version_id, constants.FileType.SAVEGAME)

    def _prompt_for_game_binary(self, version_id: int, install_path: str):
        """Prompt user to select game binary from installed files using a custom dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListView, QLabel, QDialogButtonBox, QAbstractItemView
        from turbostage.ui.game_setup_widget import BinaryListModel

        # Get list of executables from install directory
        executables = []
        for root, dirs, files in os.walk(install_path):
            for f in files:
                if f.lower().endswith((".exe", ".bat", ".com")):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, install_path)
                    executables.append(rel_path)

        if not executables:
            QMessageBox.warning(
                self,
                "No executables found",
                f"No executable files found in {install_path}. Please run the installation again.",
                QMessageBox.Ok,
            )
            return

        # First dialog: select game executable
        dialog1 = QDialog(self)
        dialog1.setWindowTitle("Select Game Executable")
        layout1 = QVBoxLayout(dialog1)
        layout1.addWidget(QLabel("Select the game executable:"))
        layout1.addWidget(
            QLabel(f"<small>Files found in: {install_path}</small>")
        )
        list_view1 = QListView(dialog1)
        model1 = BinaryListModel()
        model1.set_binaries(executables)
        list_view1.setModel(model1)
        list_view1.setSelectionMode(QAbstractItemView.SingleSelection)
        layout1.addWidget(list_view1)
        buttons1 = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog1)
        layout1.addWidget(buttons1)
        buttons1.accepted.connect(dialog1.accept)
        buttons1.rejected.connect(dialog1.reject)

        if dialog1.exec() != QDialog.Accepted:
            return

        selected = list_view1.selectedIndexes()
        if not selected:
            return
        game_exe = model1.binaries[selected[0].row()]

        # Second dialog: optional config executable
        reply = QMessageBox.question(
            self,
            "Select Config Executable",
            "Do you want to select a configuration/setup executable?",
            QMessageBox.Yes | QMessageBox.No,
        )

        config_exe = ""
        if reply == QMessageBox.Yes:
            dialog2 = QDialog(self)
            dialog2.setWindowTitle("Select Config Executable")
            layout2 = QVBoxLayout(dialog2)
            layout2.addWidget(QLabel("Select the configuration executable (optional):"))
            list_view2 = QListView(dialog2)
            model2 = BinaryListModel()
            model2.set_binaries(executables)
            list_view2.setModel(model2)
            list_view2.setSelectionMode(QAbstractItemView.SingleSelection)
            layout2.addWidget(list_view2)
            buttons2 = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog2)
            layout2.addWidget(buttons2)
            buttons2.accepted.connect(dialog2.accept)
            buttons2.rejected.connect(dialog2.reject)

            if dialog2.exec() == QDialog.Accepted:
                selected2 = list_view2.selectedIndexes()
                if selected2:
                    config_exe = model2.binaries[selected2[0].row()]

        # Store installed executables in local_versions (not versions table, to preserve original defaults)
        self._gamedb.set_local_executables(version_id, executable=game_exe, config_executable=config_exe)
        self._gamedb.mark_installed(version_id)

    def on_game_change(self):
        selected_items = self.game_table.selectedItems()
        if not selected_items:
            self._game_info.clear_info()
            self._game_info.set_game_name("Select a game to see details here.")
            self.right_setup_tab.set_game(None, None)
            self.launch_button.setEnabled(False)
            return
        if len(selected_items) != 4:
            raise RuntimeError("Invalid game selection")
        if self._current_fetch_cancel_flag is not None:
            self._current_fetch_cancel_flag.cancelled = True

        name_row = selected_items[0]
        user_data = name_row.data(Qt.UserRole)
        if len(user_data) == 4:
            igdb_id, version_id, needs_install, is_downloadable = user_data
        elif len(user_data) == 3:
            igdb_id, version_id, needs_install = user_data
            is_downloadable = False
        else:
            igdb_id, version_id = user_data
            needs_install = False
            is_downloadable = False
        game_name = name_row.text()

        self._game_info.set_game_name(game_name)
        if is_downloadable:
            self.right_setup_tab.set_game(None, self._gamedb)
        else:
            self.right_setup_tab.set_game(igdb_id, self._gamedb)

        settings = QSettings("jberclaz", "TurboStage")
        dosbox_exec = str(settings.value("app/emulator_path", ""))

        # Update launch button based on installation status
        if is_downloadable:
            self.launch_button.setText("Download Game")
            self.launch_button.setEnabled(True)
        elif needs_install:
            self.launch_button.setText("Install Game")
            self.launch_button.setEnabled(dosbox_exec != "")
        else:
            self.launch_button.setText("Launch Game")
            self.launch_button.setEnabled(dosbox_exec != "")

        # Store current game info for launch
        self._current_version_id = version_id
        self._current_needs_install = needs_install
        self._current_is_downloadable = is_downloadable

        cancel_flag = utils.CancellationFlag()
        fetch_worker = FetchGameInfoWorker(igdb_id, self._igdb_client, self.db_path, cancel_flag)
        self._current_fetch_cancel_flag = cancel_flag
        fetch_worker.finished.connect(self._game_info.set_game_info)
        fetch_task = FetchGameInfoTask(fetch_worker)
        self._thread_pool.start(fetch_task)

    def load_games(self):
        local_games = self._gamedb.get_games_with_local_versions()
        downloadable_games = self._gamedb.get_downloadable_games()
        all_games = local_games + downloadable_games

        self.game_table.setSortingEnabled(False)
        self.game_table.setRowCount(len(all_games))
        for row_num, game in enumerate(all_games):
            game_title = QTableWidgetItem(game.title)

            # Check if this game needs installation (ISO with requires_install flag and not yet installed)
            archive_type = self._gamedb.get_archive_type(game.version_id)
            requires_install = self._gamedb.get_requires_install(game.version_id)
            needs_install = False
            if archive_type == "iso" and requires_install:
                is_installed, _ = self._gamedb.get_installation_status(game.version_id)
                needs_install = not is_installed

            is_downloadable = game.download_url is not None

            # Store version_id, igdb_id, installation status, and downloadable flag
            game_title.setData(Qt.UserRole, (game.igdb_id, game.version_id, needs_install, is_downloadable))

            dt_object = datetime.fromtimestamp(game.release_date, timezone.utc)
            release_date = dt_object.strftime("%Y-%m-%d")

            self.game_table.setItem(row_num, 0, game_title)
            self.game_table.setItem(row_num, 1, QTableWidgetItem(release_date))
            self.game_table.setItem(row_num, 2, QTableWidgetItem(game.genre))
            self.game_table.setItem(row_num, 3, QTableWidgetItem(game.version))

            # Mark games that need installation
            if needs_install:
                game_title.setToolTip("Click 'Install' to install this game")
                for col in range(4):
                    item = self.game_table.item(row_num, col)
                    if item:
                        item.setForeground(Qt.gray)

            # Mark downloadable games (not yet locally present)
            if is_downloadable:
                game_title.setToolTip("Click 'Download' to get this game")
                faded = QColor(180, 180, 180)
                for col in range(4):
                    item = self.game_table.item(row_num, col)
                    if item:
                        item.setForeground(faded)
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
        local_game_archives = [file for file in os.listdir(games_path) if file.endswith((".zip", ".iso"))]

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
        dialog = LockedFileDialog(self, "Select game archive", games_path, "Game archives (*.zip *.iso)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if not dialog.exec():
            return
        game_path = dialog.selectedFiles()[0]

        # Compute hashes based on archive type
        from turbostage import iso_utils

        if iso_utils.is_iso_file(game_path):
            hashes = iso_utils.compute_hash_for_largest_files_in_iso(game_path, 4)
            archive_type = "iso"
        else:
            hashes = utils.compute_hash_for_largest_files_in_zip(game_path, 4)
            archive_type = "zip"

        version_id = self._gamedb.find_game_by_hashes([h[2] for h in hashes])
        if version_id is not None:
            requires_install = archive_type == "iso"
            added = self._gamedb.add_local_game_version(
                version_id, os.path.basename(game_path), archive_type=archive_type,
                requires_install=requires_install,
            )
            if added == 0:
                QMessageBox.warning(
                    self, "Game already installed", "The game you tried to add is already installed in TurboStage"
                )
                return
            if requires_install:
                app_data_folder = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
                installs_folder = os.path.join(app_data_folder, "installs")
                os.makedirs(installs_folder, exist_ok=True)
                install_path = os.path.join(installs_folder, str(version_id))
                if os.path.isdir(install_path):
                    import shutil
                    shutil.rmtree(install_path)
                os.makedirs(install_path, exist_ok=True)
                self._gamedb.create_installation(version_id, install_path)
            QMessageBox.information(
                self,
                "New game added",
                "New game added to game list",
            )
            self._on_game_added()
            return
        new_game_wizard = NewGameWizard(self._igdb_client, game_path, self)
        if new_game_wizard.exec() != QDialog.Accepted:
            return

        add_game_worker = AddGameWorker(
            new_game_wizard.game_title,
            new_game_wizard.game_version,
            new_game_wizard.igdb_id,
            game_path,
            new_game_wizard.game_executable,
            new_game_wizard.game_config,
            list(CPU_CYCLES.values())[new_game_wizard.cpu],
            new_game_wizard.dosbox_config,
            self.db_path,
            self._igdb_client,
            new_game_wizard.requires_install,
        )
        add_game_worker.signals.task_finished.connect(self._on_game_added)
        self._thread_pool.start(add_game_worker)

        self.status.showMessage("Adding new game...", 3000)
        QGuiApplication.setOverrideCursor(Qt.BusyCursor)

    def _on_game_added(self):
        self.load_games()
        self.on_game_change()
        QGuiApplication.restoreOverrideCursor()  # Restore normal cursor
        self.status.showMessage("New game added.", 3000)

    def _on_show_settings_dialog(self):
        dialog = SettingsDialog()
        dialog.exec()

    def _on_update_game_database(self):
        local_version = self._gamedb.get_version()

        response = requests.get(self.ONLINE_DB_URL)
        if response.status_code != 200:
            QMessageBox.critical(
                self,
                "Online database unavailable",
                "Unable to access online database. Please retry in a few minutes.",
                QMessageBox.Ok,
            )
        data = gzip.decompress(response.content)
        database = json.loads(data.decode("utf-8"))
        self._gamedb.merge_remote_json(database, self._igdb_client)

        QMessageBox.information(
            self, "Database updated", "The game database has been updated to the latest version.", QMessageBox.Ok
        )
        self.load_games()

    def _on_show_context_menu(self, pos):
        selected_items = self.game_table.selectedItems()
        if not selected_items:
            return

        name_row = selected_items[0]
        user_data = name_row.data(Qt.UserRole)
        if len(user_data) == 4:
            _, version_id, _, is_downloadable = user_data
        elif len(user_data) == 3:
            _, version_id, _ = user_data
            is_downloadable = False
        else:
            _, version_id = user_data
            is_downloadable = False

        context_menu = QMenu(self)

        if is_downloadable:
            download_action = QAction("Download", self)
            download_action.triggered.connect(self._on_download_game)
            context_menu.addAction(download_action)
        else:
            # Check if this is an installed ISO game that can be reinstalled/uninstalled
            archive_type = self._gamedb.get_archive_type(version_id)
            is_installed_iso = False
            if archive_type == "iso":
                requires_install = self._gamedb.get_requires_install(version_id)
                if requires_install:
                    installed, _ = self._gamedb.get_installation_status(version_id)
                    is_installed_iso = installed

            setup_action = QAction("Run Game Setup", self)
            setup_action.triggered.connect(self._on_run_game_setup)
            context_menu.addAction(setup_action)

            if is_installed_iso:
                reinstall_action = QAction("Reinstall", self)
                reinstall_action.triggered.connect(self._on_reinstall_game)
                context_menu.addAction(reinstall_action)

                uninstall_action = QAction("Uninstall", self)
                uninstall_action.triggered.connect(self._on_uninstall_game)
                context_menu.addAction(uninstall_action)

            delete_action = QAction("Delete Game", self)
            delete_action.triggered.connect(self._on_delete_selected_game)
            context_menu.addAction(delete_action)

        context_menu.exec(self.game_table.mapToGlobal(pos))

    def _on_delete_selected_game(self):
        game_id, version_id, game_name = self.selected_game

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to remove '{game_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Clean up installation files if this game was installed
            is_installed, install_path = self._gamedb.get_installation_status(version_id)
            if install_path:
                self._gamedb.delete_installation(version_id)
                if os.path.isdir(install_path):
                    import shutil
                    shutil.rmtree(install_path)
            self._gamedb.delete_local_game_by_igdb_id(game_id)
            self._game_info.clear_info()
            self._game_info.set_game_name("Select a game to see details here.")
            self.right_setup_tab.set_game(None, None)
            self.launch_button.setEnabled(False)
            self.load_games()
            self.game_table.clearSelection()
            if self.game_table.rowCount() > 0:
                self.on_game_change()

    def _on_download_game(self):
        selected_items = self.game_table.selectedItems()
        if not selected_items:
            return
        name_row = selected_items[0]
        user_data = name_row.data(Qt.UserRole)
        igdb_id, version_id, _, _ = user_data if len(user_data) == 4 else (user_data[0], user_data[1], False, False)
        game_name = name_row.text()

        download_url = self._gamedb.get_download_url(version_id)
        if not download_url:
            QMessageBox.critical(
                self,
                "Download Error",
                f"No download URL available for '{game_name}'.",
                QMessageBox.Ok,
            )
            return

        dialog = DownloaderDialog(self, f"Downloading {game_name}")
        dialog.start_download(download_url)
        if dialog.exec() != QDialog.Accepted or dialog.data_buffer is None:
            return

        # Save the downloaded file to the games folder
        games_path = self.games_path
        if not games_path:
            QMessageBox.critical(
                self,
                "Games folder not set",
                "Please set the games folder in Settings before downloading.",
                QMessageBox.Ok,
            )
            return

        filename = os.path.basename(download_url.split("?")[0])
        filepath = os.path.join(games_path, filename)

        try:
            with open(filepath, "wb") as f:
                f.write(dialog.data_buffer.getvalue())
        except OSError as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save downloaded file: {e}",
                QMessageBox.Ok,
            )
            return

        # Add to local versions
        archive_type = "iso" if filename.lower().endswith(".iso") else "zip"
        self._gamedb.add_local_game_version(version_id, filename, archive_type=archive_type)

        QMessageBox.information(
            self,
            "Download Complete",
            f"'{game_name}' has been downloaded successfully.",
            QMessageBox.Ok,
        )

        self._on_game_added()

    def _on_reinstall_game(self):
        _, version_id, game_name = self.selected_game

        reply = QMessageBox.question(
            self,
            "Confirm Reinstallation",
            f"Are you sure you want to reinstall '{game_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        is_installed, install_path = self._gamedb.get_installation_status(version_id)
        if install_path:
            self._gamedb.create_installation(version_id, install_path)

        self._current_version_id = version_id
        self._current_needs_install = True
        self.launch_game()

    def _on_uninstall_game(self):
        _, version_id, game_name = self.selected_game

        reply = QMessageBox.question(
            self,
            "Confirm Uninstall",
            f"Are you sure you want to uninstall '{game_name}'? This will remove all installed files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        is_installed, install_path = self._gamedb.get_installation_status(version_id)

        self._gamedb.delete_installation(version_id)

        if install_path and os.path.isdir(install_path):
            import shutil
            shutil.rmtree(install_path)

        self.load_games()
        self.on_game_change()

    def _on_run_game_setup(self):
        game_id, version_id, _ = self.selected_game
        versions = self._gamedb.get_all_game_versions(game_id, True)
        if not versions:
            return

        version_info = None
        for v in versions:
            if v.version_id == version_id:
                version_info = v
                break
        if version_info is None:
            return
        game_archive = version_info.archive

        settings = QSettings("jberclaz", "TurboStage")
        games_path = str(settings.value("app/games_path", ""))

        game_archive_url = os.path.join(games_path, game_archive)
        if version_info.config_executable is None:
            setup_dialog = GameSetupDialog(game_archive_url)
            if setup_dialog.exec() != QDialog.Accepted:
                return
            config_executable = setup_dialog.selected_binary
        else:
            config_executable = version_info.config_executable
        # For ISO games that need installation, run setup in install mode
        # so C: drive points to the persistent install path
        archive_type = self._gamedb.get_archive_type(version_id)
        needs_install = False
        if archive_type == "iso":
            requires_install = self._gamedb.get_requires_install(version_id)
            if requires_install:
                is_installed, _ = self._gamedb.get_installation_status(version_id)
                needs_install = not is_installed

        gl = GameLauncher(track_change=True)
        gl.launch_game(version_id, self._gamedb, False, False, config_executable, install_mode=needs_install)
        if gl.new_files or gl.modified_files:
            config_files = {**gl.new_files, **gl.modified_files}
            self._gamedb.add_extra_files(config_files, version_id, constants.FileType.CONFIG)

    def _on_game_settings_saved(self):
        version_id = self.right_setup_tab.version_id
        binary = self.right_setup_tab.selected_binary
        config = self.right_setup_tab.dosbox_config_text.toPlainText()
        cycles = self.right_setup_tab.cpu_cycles
        self._gamedb.update_version_info(version_id, None, binary, config, cycles)

    def _on_submit_local_config(self):
        local_versions = self._gamedb.get_locally_modified_game_versions()
        if not local_versions:
            QMessageBox.information(
                self,
                "No local configuration to upload",
                "There are no local configuration to upload.",
                QMessageBox.Ok,
            )
            return
        dlg = SubmitLocalConfigDialog(local_versions, self)
        dlg.configsSelected.connect(self._export_and_open_github)
        dlg.exec()

    def _export_and_open_github(self, version_ids):
        export = RemoteDB(self._gamedb).export_specific_versions(version_ids)
        RemoteDB.open_github_with_payload(self, json.dumps(export))

    @property
    def db_path(self):
        p = os.path.join(self._app_data_folder, self.DB_FILE)
        if not os.path.isfile(p):
            DatabaseManager.initialize_database(p)
        return p

    @property
    def games_path(self) -> str:
        settings = QSettings("jberclaz", "TurboStage")
        return str(settings.value("app/games_path", ""))

    @property
    def selected_game(self) -> tuple[int, int, str]:
        selected_items = self.game_table.selectedItems()
        if len(selected_items) != 4:
            raise RuntimeError("Invalid game selection")
        name_row = selected_items[0]
        user_data = name_row.data(Qt.UserRole)
        if len(user_data) >= 3:
            game_id, version_id, _ = user_data[:3]
        else:
            game_id, version_id = user_data
        game_name = name_row.text()
        return game_id, version_id, game_name
