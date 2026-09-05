import importlib.resources
import os
import shutil
import sys
import tempfile
import time
import zipfile

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSettings, QTimer, Signal
from PySide6.QtGui import QGuiApplication, Qt
from PySide6.QtWidgets import QMessageBox

from turbostage import constants, utils
from turbostage.db.game_database import GameDatabase

# A game that runs for less than this many seconds is considered to have
# exited immediately, usually because it failed to start correctly.
IMMEDIATE_EXIT_SECONDS = 5.0

# Grace period between terminate() and kill() in stop().
STOP_KILL_DELAY_MS = 5000


def is_midi_device_available(midi_device: int, mt32_roms_path: str, soundcanvas_roms_path: str) -> bool:
    """Check if the ROMs for a given MIDI device are installed.

    Args:
        midi_device: MIDI device (0=None, 1=MT-32, 2=Sound Canvas).
        mt32_roms_path: Path to MT-32 ROM directory.
        soundcanvas_roms_path: Path to SoundCanvas ROM directory.

    Returns:
        True if the device is None or if the corresponding ROMs are available.
    """
    if midi_device == 0:
        return True
    if midi_device == 1:
        return bool(mt32_roms_path) and os.path.isdir(mt32_roms_path) and os.listdir(mt32_roms_path)
    if midi_device == 2:
        return (
            bool(soundcanvas_roms_path) and os.path.isdir(soundcanvas_roms_path) and os.listdir(soundcanvas_roms_path)
        )
    return False


def build_dosbox_command(
    dosbox_exec: str,
    base_conf: str | None = None,
    full_screen: bool = False,
    extra_conf: str | None = None,
) -> list[str]:
    """Build the DOSBox command line (program + arguments)."""
    command = [dosbox_exec, "--noprimaryconf"]
    if base_conf:
        command.extend(["--conf", base_conf])
    if full_screen:
        command.append("--fullscreen")
    if extra_conf:
        command.extend(["--conf", extra_conf])
    return command


def build_iso_autoexec(c_drive_path: str, archive_path: str, executable: str | None, is_installed: bool) -> list[str]:
    """Build the autoexec commands used to mount and start an ISO game."""
    commands = [f'mount c "{c_drive_path}"']
    if archive_path.lower().endswith(".iso"):
        commands.append(f'imgmount d "{archive_path}" -t iso')
    else:
        commands.append(f'mount d "{archive_path}" -t cdrom')
    # Normalize the executable path to DOS style: strip the ISO version
    # number (e.g. ";1"), leading separators and convert '/' to '\' so the
    # autoexec 'cd' command works regardless of how the path was stored.
    exec_path = executable.split(";")[0] if executable else ""
    exec_path = exec_path.replace("/", "\\").strip("\\")
    if "\\" in exec_path:
        exec_dir, exec_name = exec_path.rsplit("\\", 1)
    else:
        exec_dir, exec_name = "", exec_path

    commands.append("c:" if is_installed else "d:")
    if exec_dir:
        commands.append(f"cd {exec_dir}")
    commands.append(exec_name)
    return commands


def _dosbox_process_env() -> QProcessEnvironment | None:
    """Return a sanitized process environment for launching DOSBox, or None if unneeded.

    PyInstaller prepends its extraction directory to LD_LIBRARY_PATH so the
    bundled Qt/OpenGL libraries can be found. If DOSBox inherits that value it
    loads the bundled GL libraries (which do not provide GLX) and aborts with
    "Couldn't find matching GLX visual". Strip the bundle directory from
    LD_LIBRARY_PATH before spawning DOSBox.
    """
    if not sys.platform.startswith("linux"):
        return None

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if not bundle_dir:
        return None

    env = QProcessEnvironment.systemEnvironment()
    ld_library_path = env.value("LD_LIBRARY_PATH")
    if not ld_library_path:
        return env

    bundle_dir = os.path.abspath(bundle_dir)
    entries = [p for p in ld_library_path.split(os.pathsep) if p and os.path.abspath(p) != bundle_dir]
    if entries:
        env.insert("LD_LIBRARY_PATH", os.pathsep.join(entries))
    else:
        env.remove("LD_LIBRARY_PATH")
    return env


class GameLauncher(QObject):
    """Launch DOSBox asynchronously via QProcess so the UI stays responsive.

    Emits finished(installation_completed, install_path) when the DOSBox
    process ends, whether it exited cleanly, crashed, or was stopped.
    """

    finished = Signal(bool, object)

    def __init__(self, track_change: bool = False, parent: QObject | None = None):
        super().__init__(parent)
        self._track_change = track_change
        self._original_files = {}
        self._new_files = {}
        self._modified_files = {}
        self._version_id = None
        self._process: QProcess | None = None
        self._temp_dir: str | None = None
        self._conf_path: str | None = None
        self._start_time = 0.0
        self._install_mode = False
        self._was_installed = False
        self._install_path: str | None = None
        self._stopped_by_user = False
        self._finalized = False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    def stop(self):
        """Ask DOSBox to terminate, escalating to kill after a grace period."""
        self._stopped_by_user = True
        if self.is_running:
            self._process.terminate()
            QTimer.singleShot(STOP_KILL_DELAY_MS, self._kill_if_running)

    def _kill_if_running(self):
        if self.is_running:
            self._process.kill()

    def launch_game(
        self,
        version_id: int,
        db: GameDatabase,
        save_games: bool = True,
        config_files: bool = True,
        binary: str | None = None,
        install_mode: bool = False,
    ) -> bool:
        """Start a game without blocking. Returns True if DOSBox was started.

        Results (changed files, installation outcome) are delivered through
        the finished signal; read new_files/modified_files/version_id there.
        """
        if self.is_running:
            return False

        QGuiApplication.setOverrideCursor(Qt.BusyCursor)

        game_info = db.get_version_by_version_id(version_id)

        executable = game_info.executable
        archive = game_info.archive
        config = game_info.config
        cpu_cycles = game_info.cycles
        midi_device = game_info.midi_device or 0
        self._version_id = game_info.version_id
        if binary is not None:
            executable = binary

        settings = QSettings("jberclaz", "TurboStage")
        full_screen = utils.to_bool(settings.value("app/full_screen", False)) and binary is None
        dosbox_exec = str(settings.value("app/emulator_path", ""))
        games_path = str(settings.value("app/games_path", ""))
        mt32_roms_path = str(settings.value("app/mt32_path", ""))
        soundcanvas_roms_path = str(settings.value("app/soundcanvas_path", ""))
        disk_noise = utils.to_bool(settings.value("app/disk_noise", False))

        # Revert MIDI device to None if ROMs are not available
        if not is_midi_device_available(midi_device, mt32_roms_path, soundcanvas_roms_path):
            midi_device = 0

        if not dosbox_exec:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(
                None,
                "DosBox binary not specified",
                "Cannot start game, because the DosBox Staging binary has not been specified. Use the Settings dialog to set it up or download DosBox Staging",
                QMessageBox.Ok,
            )
            return False

        self._install_mode = install_mode
        self._stopped_by_user = False
        self._finalized = False

        # Get archive type from database
        archive_type = db.get_archive_type(version_id)

        main_config = str(importlib.resources.files("turbostage").joinpath("conf/dosbox-staging.conf"))

        # The temp dir outlives this call on purpose: it is removed in
        # _on_process_finished once DOSBox has exited.
        self._temp_dir = tempfile.mkdtemp()
        temp_dir = self._temp_dir
        archive_path = os.path.join(games_path, archive)

        try:
            if archive_type == "iso":
                command = self._prepare_iso_game(
                    db,
                    dosbox_exec,
                    main_config,
                    full_screen,
                    temp_dir,
                    archive_path,
                    executable,
                    config,
                    mt32_roms_path,
                    soundcanvas_roms_path,
                    disk_noise,
                    cpu_cycles,
                    midi_device,
                    save_games,
                    config_files,
                )
            else:
                command = self._prepare_zip_game(
                    db,
                    dosbox_exec,
                    main_config,
                    full_screen,
                    temp_dir,
                    archive_path,
                    executable,
                    config,
                    mt32_roms_path,
                    soundcanvas_roms_path,
                    disk_noise,
                    cpu_cycles,
                    midi_device,
                    save_games,
                    config_files,
                )
        except (OSError, zipfile.BadZipFile) as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(
                None,
                "Cannot start game",
                f"Failed to prepare the game files: '{e}'",
                QMessageBox.Ok,
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._temp_dir = None
            return False

        self._process = QProcess(self)
        self._process.started.connect(self._on_process_started)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        process_env = _dosbox_process_env()
        if process_env is not None:
            self._process.setProcessEnvironment(process_env)
        self._start_time = time.monotonic()
        self._process.setProgram(command[0])
        self._process.setArguments(command[1:])
        self._process.start()
        return True

    def _prepare_zip_game(
        self,
        db,
        dosbox_exec,
        main_config,
        full_screen,
        temp_dir,
        archive_path,
        executable,
        config,
        mt32_roms_path,
        soundcanvas_roms_path,
        disk_noise,
        cpu_cycles,
        midi_device,
        save_games,
        config_files,
    ):
        """Extract a ZIP game and build its DOSBox command."""
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        if config_files:
            GameLauncher._write_game_extra_files(self._version_id, temp_dir, db, constants.FileType.CONFIG)

        if save_games:
            GameLauncher._write_game_extra_files(self._version_id, temp_dir, db, constants.FileType.SAVEGAME)

        if self._track_change:
            self._original_files = utils.list_files_with_md5(temp_dir)

        self._conf_path = self._write_extra_conf(
            config, mt32_roms_path, soundcanvas_roms_path, disk_noise, cpu_cycles, midi_device
        )
        command = build_dosbox_command(dosbox_exec, main_config, full_screen, self._conf_path)
        command.append(os.path.join(temp_dir, executable))
        return command

    def _prepare_iso_game(
        self,
        db,
        dosbox_exec,
        main_config,
        full_screen,
        temp_dir,
        archive_path,
        executable,
        config,
        mt32_roms_path,
        soundcanvas_roms_path,
        disk_noise,
        cpu_cycles,
        midi_device,
        save_games,
        config_files,
    ):
        """Mount an ISO game and build its DOSBox command."""
        # Get installation status
        is_installed, install_path = db.get_installation_status(self._version_id)
        self._was_installed = bool(is_installed)
        self._install_path = install_path

        # Determine what to mount as C: drive
        if self._install_mode and not is_installed:
            # Installation mode: C: is the installation directory (to persist files)
            c_drive_path = install_path
        elif not is_installed:
            # Not installed and not in install mode: use temp directory
            c_drive_path = temp_dir
        else:
            # Normal mode: C: is the installation directory
            c_drive_path = install_path

        if config_files:
            GameLauncher._write_game_extra_files(self._version_id, c_drive_path, db, constants.FileType.CONFIG)
        if save_games:
            GameLauncher._write_game_extra_files(self._version_id, c_drive_path, db, constants.FileType.SAVEGAME)

        autoexec_commands = build_iso_autoexec(c_drive_path, archive_path, executable, bool(is_installed))

        extra_conf = self._write_extra_conf(
            config, mt32_roms_path, soundcanvas_roms_path, disk_noise, cpu_cycles, midi_device
        )
        with tempfile.NamedTemporaryFile(suffix=".conf", mode="wt", delete=False) as conf_file:
            if extra_conf:
                with open(extra_conf) as extra:
                    conf_file.write(extra.read())
                os.unlink(extra_conf)
            conf_file.write("\n[autoexec]\n" + "\n".join(autoexec_commands) + "\n")
            self._conf_path = conf_file.name

        return build_dosbox_command(dosbox_exec, main_config, full_screen, self._conf_path)

    def _write_extra_conf(
        self, config, mt32_roms_path, soundcanvas_roms_path, disk_noise, cpu_cycles, midi_device
    ) -> str | None:
        if not (config or mt32_roms_path or soundcanvas_roms_path or disk_noise or cpu_cycles > 0 or midi_device > 0):
            return None
        with tempfile.NamedTemporaryFile(suffix=".conf", mode="wt", delete=False) as conf_file:
            GameLauncher._write_custom_dosbox_config_file(
                conf_file,
                config,
                mt32_roms_path,
                soundcanvas_roms_path,
                disk_noise,
                cpu_cycles,
                midi_device,
            )
            return conf_file.name

    def _on_process_started(self):
        # The game window is up; the busy cursor has served its purpose.
        QGuiApplication.restoreOverrideCursor()

    def _on_process_error(self, error: QProcess.ProcessError):
        if error == QProcess.ProcessError.FailedToStart:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(
                None,
                "Error in DosBox",
                "Failed to start DOSBox. Check the emulator path in Settings.",
                QMessageBox.Ok,
            )
            self._finalize(False, None)

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if self._finalized:
            # Already handled via errorOccurred (e.g. FailedToStart).
            return
        crashed = exit_status != QProcess.ExitStatus.NormalExit
        if not self._stopped_by_user:
            if crashed or exit_code != 0:
                QMessageBox.warning(
                    None,
                    "Error in DosBox",
                    f"The game failed with exit code {exit_code}.",
                    QMessageBox.Ok,
                )
            elif not self._install_mode and time.monotonic() - self._start_time < IMMEDIATE_EXIT_SECONDS:
                self._warn_immediate_exit()

        installation_completed = False
        result_install_path = None
        if self._install_mode and not self._was_installed and not crashed and exit_code == 0:
            installation_completed = True
            result_install_path = self._install_path

        self._finalize(installation_completed, result_install_path)

    def _finalize(self, installation_completed: bool, install_path: str | None):
        # finished and errorOccurred can both fire; run cleanup exactly once.
        if self._finalized:
            return
        self._finalized = True
        try:
            if self._track_change and self._temp_dir and os.path.isdir(self._temp_dir):
                self._extract_changed_files(self._temp_dir)
        finally:
            if self._conf_path and os.path.isfile(self._conf_path):
                os.unlink(self._conf_path)
            self._conf_path = None
            if self._temp_dir and os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
        self.finished.emit(installation_completed, install_path)

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
    def _write_custom_dosbox_config_file(
        config_file,
        config_content: str | None,
        mt32_roms_path: str,
        soundcanvas_roms_path: str,
        disk_noise: bool,
        cpu_cycles: int,
        midi_device: int = 0,
    ):
        # Write MIDI device setting first so it takes precedence over free-form config
        if midi_device == 1:
            config_file.write("\n[midi]\nmididevice = mt32\n")
        elif midi_device == 2:
            config_file.write("\n[midi]\nmididevice = soundcanvas\n")
        if config_content:
            config_file.write(config_content)
        if cpu_cycles > 0:
            config_file.write(f"\n[cpu]\ncpu_cycles = {cpu_cycles}\ncpu_cycles_protected = {cpu_cycles}\n")
        if mt32_roms_path:
            config_file.write(f"\n[mt32]\nromdir = {mt32_roms_path}\n")
        if soundcanvas_roms_path:
            config_file.write(f"\n[soundcanvas]\nsoundcanvas_rom_dir = {soundcanvas_roms_path}\n")
        if disk_noise:
            config_file.write("\n[disknoise]\nhard_disk_noise = on\nfloppy_disk_noise = on\n")
        config_file.flush()

    @staticmethod
    def _warn_immediate_exit():
        QMessageBox.information(
            None,
            "Game exited immediately",
            "The game stopped almost immediately after starting. This usually means it "
            "needs to be configured or installed first. Try running its setup program "
            "(right-click the game and choose 'Run Game Setup').",
            QMessageBox.Ok,
        )

    @property
    def modified_files(self) -> dict:
        return self._modified_files

    @property
    def new_files(self) -> dict:
        return self._new_files

    @property
    def version_id(self) -> int | None:
        return self._version_id
