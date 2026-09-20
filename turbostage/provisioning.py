"""Shared provisioning helpers: downloads, archive extraction, install dirs.

SettingsDialog and SetupWizard previously triple-duplicated the DOSBox /
MT-32 / SoundCanvas download+extract logic (including tar-slip and unbound
executable hazards). MainWindow and AddGameWorker duplicated the
installs/<version_id> directory setup. This module is the single source.
"""

import glob
import logging
import lzma
import os
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from io import BytesIO
from zipfile import ZipFile

from PySide6.QtCore import QStandardPaths

from turbostage import constants

logger = logging.getLogger(__name__)

SOUNDCANVAS_ROMS_SUBPATH = os.path.join("Nuked-SC55-CLAP-ROM-files", "Nuked-SC55-Resources", "ROMs")


def app_subdir(name: str) -> str:
    """Return (creating) a subdirectory of the app-data folder."""
    base = os.path.dirname(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    return path


def dosbox_download_url(os_name: str) -> str:
    """Return the DOSBox Staging download URL for an OS name."""
    if os_name == "Linux":
        return constants.DOSBOX_STAGING_LINUX
    if os_name == "Windows":
        return constants.DOSBOX_STAGING_WINDOWS
    if os_name == "Darwin":
        return constants.DOSBOX_STAGING_MACOS
    raise OSError(f"Unsupported operating system: {os_name}")


def _safe_extract_zip(zip_file: ZipFile, dest_dir: str) -> None:
    """Extract a ZIP with zip-slip protection."""
    for info in zip_file.infolist():
        name = info.filename.replace("\\", "/").strip()
        if not name or os.path.isabs(name) or ".." in name.split("/"):
            raise OSError(f"Unsafe path in archive: '{info.filename}'")
    zip_file.extractall(dest_dir)


def safe_extract_zip(zip_file: ZipFile, dest_dir: str) -> None:
    """Public zip-slip-guarded extraction (also used by the game launcher)."""
    _safe_extract_zip(zip_file, dest_dir)


def extract_dosbox_archive(data: BytesIO, dest_dir: str, os_name: str) -> str:
    """Extract a downloaded DOSBox archive; return the relative executable path.

    Raises OSError with a human-readable message when the layout is
    unexpected (previously an UnboundLocalError) or extraction fails.
    """
    os.makedirs(dest_dir, exist_ok=True)
    data.seek(0)
    executable = ""
    try:
        if os_name == "Linux":
            with lzma.open(data, "rb") as f:
                with tarfile.open(fileobj=f, mode="r|*") as tar:
                    _safe_extract_tar(tar, dest_dir)
                    for member in tar.getmembers():
                        if member.name.endswith("/dosbox"):
                            executable = member.name
                            break
        elif os_name == "Windows":
            with ZipFile(data, "r") as zip_ref:
                _safe_extract_zip(zip_ref, dest_dir)
                for filename in zip_ref.namelist():
                    if filename.endswith("/dosbox.exe"):
                        executable = filename
                        break
        elif os_name == "Darwin":
            executable = _extract_dmg(data, dest_dir)
        else:
            raise OSError(f"Unsupported operating system: {os_name}")
    except (tarfile.TarError, lzma.LZMAError, zipfile.BadZipFile, OSError) as e:
        raise OSError(f"Could not extract DOSBox archive: {e}") from e
    if not executable:
        raise OSError("Download finished but the DOSBox executable was not found in the archive.")
    return executable


def _safe_extract_tar(tar: tarfile.TarFile, dest_dir: str) -> None:
    """Extract a tar with traversal protection (filter='data' when available)."""
    try:
        tar.extractall(path=dest_dir, filter="data")
    except TypeError:
        # Python < 3.12 without the filter argument: validate manually.
        for member in tar.getmembers():
            name = member.name.replace("\\", "/").strip()
            if not name or os.path.isabs(name) or ".." in name.split("/"):
                raise OSError(f"Unsafe path in archive: '{member.name}'")
        tar.extractall(path=dest_dir)


def _extract_dmg(data: BytesIO, dest_dir: str) -> str:
    """Extract the macOS DMG via hdiutil; return the relative executable path."""
    data.seek(0)
    with tempfile.NamedTemporaryFile(suffix=".dmg", delete=False) as tmp_dmg:
        tmp_dmg.write(data.getvalue())
        dmg_path = tmp_dmg.name
    mount_point = None
    try:
        result = subprocess.run(
            [
                "hdiutil",
                "attach",
                "-plist",
                "-nobrowse",
                "-mountrandom",
                "/tmp",
                dmg_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        plist = plistlib.loads(result.stdout.encode())
        mount_point = next(
            (e["mount-point"] for e in plist.get("system-entities", []) if "mount-point" in e),
            None,
        )
        if not mount_point:
            raise OSError("Could not mount the DOSBox disk image.")
        app_bundles = glob.glob(os.path.join(mount_point, "*.app"))
        if not app_bundles:
            raise OSError("No application bundle found in the disk image.")
        app_bundle = app_bundles[0]
        target_app = os.path.join(dest_dir, os.path.basename(app_bundle))
        if os.path.exists(target_app):
            shutil.rmtree(target_app)
        subprocess.run(["cp", "-R", app_bundle, target_app], check=True)
        macos_dir = os.path.join(target_app, "Contents", "MacOS")
        try:
            executables = sorted(os.listdir(macos_dir))
        except OSError as e:
            raise OSError(f"Application bundle has no executables: {e}") from e
        if not executables:
            raise OSError("Application bundle has no executables.")
        return os.path.join(os.path.basename(app_bundle), "Contents", "MacOS", executables[0])
    finally:
        if mount_point:
            try:
                subprocess.run(["hdiutil", "detach", mount_point], check=True)
            except subprocess.CalledProcessError as e:
                logger.warning("Failed to detach disk image %s: %s", mount_point, e)
        try:
            os.unlink(dmg_path)
        except OSError:
            pass


def extract_mt32_roms(data: BytesIO, dest_dir: str) -> None:
    """Extract downloaded MT-32 ROMs into dest_dir."""
    os.makedirs(dest_dir, exist_ok=True)
    data.seek(0)
    try:
        with ZipFile(data, "r") as zip_ref:
            _safe_extract_zip(zip_ref, dest_dir)
    except (zipfile.BadZipFile, OSError) as e:
        raise OSError(f"Could not extract MT-32 ROMs: {e}") from e


def _find_soundcanvas_roms_src(tmp_dir: str) -> str:
    """Locate the ROMs payload inside the extracted SoundCanvas ZIP."""
    preferred = os.path.join(tmp_dir, SOUNDCANVAS_ROMS_SUBPATH)
    if os.path.isdir(preferred):
        return preferred
    # Upstream renames break the hard-coded path; fall back to any ROMs dir.
    candidates = glob.glob(os.path.join(tmp_dir, "**", "ROMs"), recursive=True)
    for candidate in sorted(candidates):
        if os.path.isdir(candidate) and os.listdir(candidate):
            logger.info("SoundCanvas ROMs found at fallback path: %s", candidate)
            return candidate
    raise OSError(
        "Downloaded SoundCanvas archive has an unexpected layout " f"(looked for '{SOUNDCANVAS_ROMS_SUBPATH}')."
    )


def extract_soundcanvas_roms(data: BytesIO, dest_dir: str) -> None:
    """Extract downloaded SoundCanvas ROMs (SC-55 folders land directly in dest)."""
    os.makedirs(dest_dir, exist_ok=True)
    data.seek(0)
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with ZipFile(data, "r") as zip_ref:
                _safe_extract_zip(zip_ref, tmp_dir)
            roms_src = _find_soundcanvas_roms_src(tmp_dir)
            for item in os.listdir(roms_src):
                src = os.path.join(roms_src, item)
                dst = os.path.join(dest_dir, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
    except (zipfile.BadZipFile, OSError) as e:
        raise OSError(f"Could not extract SoundCanvas ROMs: {e}") from e


def ensure_installation_dir(db, version_id: int) -> str:
    """Create (cleaning stale) installs/<version_id> and record it in the DB."""
    installs_folder = app_subdir("installs")
    install_path = os.path.join(installs_folder, str(version_id))
    if os.path.isdir(install_path):
        shutil.rmtree(install_path)
    os.makedirs(install_path, exist_ok=True)
    db.create_installation(version_id, install_path)
    return install_path
