import importlib
import os
import sqlite3
import subprocess
import tempfile
import zipfile

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from turbostage import constants, utils


class GameLauncher:
    def __init__(self, track_change: bool = False):
        self._track_change = track_change
        self._original_files = {}
        self._new_files = {}
        self._modified_files = {}
        self._version_id = None

    def launch_game(
        self, game_id: int, db_path: str, save_games: bool = True, config_files: bool = True, binary: str | None = None
    ):
        conn = sqlite3.connect(db_path)
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
        executable, archive, config, cpu_cycles, self._version_id = rows[0]
        if binary is not None:
            executable = binary

        settings = QSettings("jberclaz", "TurboStage")
        full_screen = utils.to_bool(settings.value("app/full_screen", False)) and binary is None
        dosbox_exec = str(settings.value("app/emulator_path", ""))
        games_path = str(settings.value("app/games_path", ""))
        mt32_roms_path = str(settings.value("app/mt32_path", ""))
        if not dosbox_exec:
            QMessageBox.critical(
                None,
                "DosBox binary not specified",
                "Cannot start game, because the DosBox Staging binary has not been specified. Use the Settings dialog to set it up or download DosBox Staging",
                QMessageBox.Ok,
            )
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(games_path, archive)
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            if config_files:
                GameLauncher._write_game_extra_files(self._version_id, temp_dir, db_path, constants.FileType.CONFIG)

            if save_games:
                GameLauncher._write_game_extra_files(self._version_id, temp_dir, db_path, constants.FileType.SAVEGAME)

            if self._track_change:
                self._original_files = utils.list_files_with_md5(temp_dir)

            executable_path = os.path.join(temp_dir, executable)
            main_config = importlib.resources.files("turbostage").joinpath("conf/dosbox-staging.conf")
            command = [dosbox_exec, "--noprimaryconf", "--conf", str(main_config)]
            if full_screen:
                command.append("--fullscreen")
            with tempfile.NamedTemporaryFile(suffix=".conf", mode="wt") as conf_file:
                if config or mt32_roms_path or cpu_cycles > 0:
                    GameLauncher._write_custom_dosbox_config_file(conf_file, config, mt32_roms_path, cpu_cycles)
                    command.extend(["--conf", conf_file.name])
                command.append(executable_path)
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

    def _extract_changed_files(self, temp_dir: str):
        files_after_setup = utils.list_files_with_md5(temp_dir)
        for file_after_setup, file_hash in files_after_setup.items():
            if not file_after_setup in self._original_files:
                with open(file_after_setup, "rb") as f:
                    content = f.read()
                self._new_files[os.path.relpath(file_after_setup, temp_dir)] = content
            elif self._original_files[file_after_setup] != file_hash:
                with open(file_after_setup, "rb") as f:
                    content = f.read()
                self._modified_files[os.path.relpath(file_after_setup, temp_dir)] = content

    @staticmethod
    def _write_game_extra_files(version_id: int, temp_dir: str, db_path: str, file_type: int):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT path, content FROM config_files
            WHERE version_id = ? AND type = ?
            """,
            (version_id, file_type),
        )
        rows = cursor.fetchall()
        conn.close()
        for config_file_path, content in rows:
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
