import importlib
import os
import sqlite3
import subprocess
import tempfile
import zipfile

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from turbostage import utils


class GameLauncher:
    @staticmethod
    def launch_game(game_id: str, db_path: str, config_files: bool = True, binary: str | None = None):
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
        executable, archive, config, cpu_cycles, version_id = rows[0]
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
                GameLauncher.write_game_config_files(version_id, temp_dir, db_path)

            executable_path = os.path.join(temp_dir, executable)
            main_config = importlib.resources.files("turbostage").joinpath("conf/dosbox-staging.conf")
            command = [dosbox_exec, "--noprimaryconf", "--conf", str(main_config)]
            if full_screen:
                command.append("--fullscreen")
            with tempfile.NamedTemporaryFile() as conf_file:
                if config or mt32_roms_path or cpu_cycles > 0:
                    GameLauncher.write_custom_dosbox_config_file(conf_file.name, config, mt32_roms_path, cpu_cycles)
                    command.extend(["--conf", conf_file.name])
                command.append(executable_path)
                subprocess.run(command)

    @staticmethod
    def write_game_config_files(version_id: int, temp_dir: str, db_path: str):
        conn = sqlite3.connect(db_path)
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

    @staticmethod
    def write_custom_dosbox_config_file(
        config_file: str, config_content: str | None, mt32_roms_path: str, cpu_cycles: int
    ):
        with open(config_file, "wt") as f:
            if config_content:
                f.write(config_content)
            if cpu_cycles > 0:
                f.write(f"\n[cpu]\ncpu_cycles = {cpu_cycles}\n")
            if mt32_roms_path:
                f.write(f"\n[mt32]\nromdir = {mt32_roms_path}\n")
