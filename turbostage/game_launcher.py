import importlib
import os
import subprocess
import tempfile
import zipfile

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication, Qt
from PySide6.QtWidgets import QMessageBox

from turbostage import constants, utils
from turbostage.db.game_database import GameDatabase


class GameLauncher:
    def __init__(self, track_change: bool = False):
        self._track_change = track_change
        self._original_files = {}
        self._new_files = {}
        self._modified_files = {}
        self._version_id = None

    def launch_game(
        self,
        version_id: int,
        db: GameDatabase,
        save_games: bool = True,
        config_files: bool = True,
        binary: str | None = None,
        install_mode: bool = False,
    ):
        """Launch a game.

        Args:
            version_id: The game version ID to launch
            db: GameDatabase instance
            save_games: Whether to load save games
            config_files: Whether to load config files
            binary: Optional override for the executable to run
            install_mode: If True, launch in installation mode (ISO games only)
        """
        QGuiApplication.setOverrideCursor(Qt.BusyCursor)

        game_info = db.get_version_by_version_id(version_id)

        executable = game_info.executable
        archive = game_info.archive
        config = game_info.config
        cpu_cycles = game_info.cycles
        self._version_id = game_info.version_id
        if binary is not None:
            executable = binary

        settings = QSettings("jberclaz", "TurboStage")
        full_screen = utils.to_bool(settings.value("app/full_screen", False)) and binary is None
        dosbox_exec = str(settings.value("app/emulator_path", ""))
        games_path = str(settings.value("app/games_path", ""))
        mt32_roms_path = str(settings.value("app/mt32_path", ""))
        if not dosbox_exec:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(
                None,
                "DosBox binary not specified",
                "Cannot start game, because the DosBox Staging binary has not been specified. Use the Settings dialog to set it up or download DosBox Staging",
                QMessageBox.Ok,
            )
            return

        # Get archive type from database
        archive_type = db.get_archive_type(version_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(games_path, archive)

            # Build DOSBox command
            main_config = importlib.resources.files("turbostage").joinpath("conf/dosbox-staging.conf")
            command = [dosbox_exec, "--noprimaryconf", "--conf", str(main_config)]

            if full_screen:
                command.append("--fullscreen")

            # Handle different archive types
            if archive_type == "iso":
                # For ISO files, we mount as CD-ROM
                self._launch_iso_game(
                    db,
                    command,
                    conf_file_path=None,
                    temp_dir=temp_dir,
                    archive_path=archive_path,
                    executable=executable,
                    config=config,
                    mt32_roms_path=mt32_roms_path,
                    cpu_cycles=cpu_cycles,
                    save_games=save_games,
                    config_files=config_files,
                    install_mode=install_mode,
                )
            else:
                # For ZIP files, extract to temp directory (existing behavior)
                self._launch_zip_game(
                    db,
                    command,
                    temp_dir=temp_dir,
                    archive_path=archive_path,
                    executable=executable,
                    config=config,
                    mt32_roms_path=mt32_roms_path,
                    cpu_cycles=cpu_cycles,
                    save_games=save_games,
                    config_files=config_files,
                )

    def _launch_zip_game(
        self,
        db,
        command,
        temp_dir,
        archive_path,
        executable,
        config,
        mt32_roms_path,
        cpu_cycles,
        save_games,
        config_files,
    ):
        """Launch a ZIP archive game by extracting to temp directory."""
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        if config_files:
            GameLauncher._write_game_extra_files(self._version_id, temp_dir, db, constants.FileType.CONFIG)

        if save_games:
            GameLauncher._write_game_extra_files(self._version_id, temp_dir, db, constants.FileType.SAVEGAME)

        if self._track_change:
            self._original_files = utils.list_files_with_md5(temp_dir)

        executable_path = os.path.join(temp_dir, executable)

        with tempfile.NamedTemporaryFile(suffix=".conf", mode="wt", delete=False) as conf_file:
            if config or mt32_roms_path or cpu_cycles > 0:
                GameLauncher._write_custom_dosbox_config_file(conf_file, config, mt32_roms_path, cpu_cycles)
                command.extend(["--conf", conf_file.name])
            command.append(executable_path)
            QGuiApplication.restoreOverrideCursor()
            try:
                subprocess.run(command, check=True)
            except subprocess.CalledProcessError as e:
                QMessageBox.warning(
                    None,
                    "Error in DosBox",
                    f"The game failed with the following error: '{e}'",
                    QMessageBox.Ok,
                )

        if self._track_change:
            self._extract_changed_files(temp_dir)

    def _launch_iso_game(
        self,
        db,
        command,
        conf_file_path,
        temp_dir,
        archive_path,
        executable,
        config,
        mt32_roms_path,
        cpu_cycles,
        save_games,
        config_files,
        install_mode,
    ):
        """Launch an ISO game by mounting as CD-ROM."""
        # Get installation status
        is_installed, install_path = db.get_installation_status(self._version_id)

        # Write config and save files to temp directory (this becomes C:)
        if config_files:
            GameLauncher._write_game_extra_files(self._version_id, temp_dir, db, constants.FileType.CONFIG)

        if save_games:
            GameLauncher._write_game_extra_files(self._version_id, temp_dir, db, constants.FileType.SAVEGAME)

        # Determine what to mount as C: drive
        if install_mode or not is_installed:
            # Installation mode: C: is the temp directory (empty or with configs/saves)
            c_drive_path = temp_dir
        else:
            # Normal mode: C: is the installation directory
            c_drive_path = install_path

        # Build autoexec commands for mounting
        autoexec_commands = []
        autoexec_commands.append(f'mount c "{c_drive_path}"')
        # For ISO files, use imgmount with -t iso
        if archive_path.lower().endswith('.iso'):
            autoexec_commands.append(f'imgmount d "{archive_path}" -t iso')
        else:
            autoexec_commands.append(f'mount d "{archive_path}" -t cdrom')
        autoexec_commands.append("d:")

        # Change to the directory containing the executable if needed
        # Strip ISO version number (e.g., ;1) from executable path
        exec_path = executable.split(";")[0]
        exec_dir = os.path.dirname(exec_path)
        if exec_dir:
            autoexec_commands.append(f"cd {exec_dir}")

        exec_name = os.path.basename(exec_path)
        autoexec_commands.append(exec_name)

        autoexec_section = "\n[autoexec]\n" + "\n".join(autoexec_commands)

        with tempfile.NamedTemporaryFile(suffix=".conf", mode="wt", delete=False) as conf_file:
            # Write custom config
            if config or mt32_roms_path or cpu_cycles > 0:
                GameLauncher._write_custom_dosbox_config_file(conf_file, config, mt32_roms_path, cpu_cycles)

            # Write autoexec section
            conf_file.write(autoexec_section)
            conf_file.flush()

            command.extend(["--conf", conf_file.name])
            QGuiApplication.restoreOverrideCursor()

            try:
                subprocess.run(command, check=True)

                # If we were in install mode and DOSBox succeeded, mark as installed
                if install_mode and not is_installed:
                    db.mark_installed(self._version_id)

            except subprocess.CalledProcessError as e:
                QMessageBox.warning(
                    None,
                    "Error in DosBox",
                    f"The game failed with the following error: '{e}'",
                    QMessageBox.Ok,
                )

    def _extract_changed_files(self, temp_dir: str):
        files_after_setup = utils.list_files_with_md5(temp_dir)
        for file_after_setup, file_hash in files_after_setup.items():
            if file_after_setup not in self._original_files:
                with open(file_after_setup, "rb") as f:
                    content = f.read()
                self._new_files[os.path.relpath(file_after_setup, temp_dir)] = content
            elif self._original_files[file_after_setup] != file_hash:
                with open(file_after_setup, "rb") as f:
                    content = f.read()
                self._modified_files[os.path.relpath(file_after_setup, temp_dir)] = content

    @staticmethod
    def _write_game_extra_files(version_id: int, temp_dir: str, db: GameDatabase, file_type: int):
        config_files = db.get_config_files_with_content(version_id, file_type)

        for config_file_path, content in config_files:
            folder = os.path.join(temp_dir, os.path.dirname(config_file_path))
            if not os.path.isdir(folder):
                os.makedirs(folder)
            with open(os.path.join(temp_dir, config_file_path), "wb") as f:
                f.write(content)

    @staticmethod
    def _write_custom_dosbox_config_file(config_file, config_content: str | None, mt32_roms_path: str, cpu_cycles: int):
        if config_content:
            config_file.write(config_content)
        if cpu_cycles > 0:
            config_file.write(f"\n[cpu]\ncpu_cycles = {cpu_cycles}\ncpu_cycles_protected = {cpu_cycles}\n")
        if mt32_roms_path:
            config_file.write(f"\n[mt32]\nromdir = {mt32_roms_path}\n")
        config_file.flush()

    @property
    def modified_files(self) -> dict:
        return self._modified_files

    @property
    def new_files(self) -> dict:
        return self._new_files

    @property
    def version_id(self) -> int | None:
        return self._version_id
