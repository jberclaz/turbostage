"""ISO utility functions for TurboStage.

This module provides utility functions for working with ISO 9660 image files,
including computing MD5 hashes, listing files, and extracting metadata.
"""

import hashlib
import logging
import os

import pycdlib
from pycdlib import pycdlibexception

logger = logging.getLogger(__name__)


def is_iso_file(file_path: str) -> bool:
    """Check if a file is an ISO image based on extension and magic bytes.

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file has a .iso extension and valid ISO magic bytes
    """
    if os.path.splitext(file_path)[1].lower() != ".iso":
        return False
    try:
        with open(file_path, "rb") as f:
            f.seek(32769)
            return f.read(5) == b"CD001"
    except (OSError, IOError):
        return False


def get_archive_type(file_path: str) -> str:
    """Determine the archive type based on file extension.

    Args:
        file_path: Path to the archive file

    Returns:
        'iso' if the file is an ISO image, 'zip' otherwise
    """
    return "iso" if is_iso_file(file_path) else "zip"


def compute_md5_from_iso(iso, file_path: str) -> str:
    """Compute the MD5 hash of a file inside an ISO archive.

    Args:
        iso: Opened pycdlib Iso object or path to ISO file
        file_path: Path to the file within the ISO

    Returns:
        MD5 hash as a hex string
    """
    import pycdlib

    hash_md5 = hashlib.md5()

    # Try different path types
    path_types = ["iso_path", "joliet_path", "rr_path"]
    # Also try with ISO 9660 version number suffix (e.g., ;1)
    paths_to_try = [file_path]
    if ";" not in file_path:
        paths_to_try.append(file_path + ";1")
    opened = False

    if isinstance(iso, str):
        # iso is a path, open it
        iso_obj = pycdlib.PyCdlib()
        iso_obj.open(iso)
        try:
            for path in paths_to_try:
                for path_type in path_types:
                    try:
                        with iso_obj.open_file_from_iso(**{path_type: path}) as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                hash_md5.update(chunk)
                            opened = True
                            break
                    except Exception:
                        continue
                if opened:
                    break
            if not opened:
                raise pycdlibexception.PyCdlibInvalidInput(f"Could not find path: {file_path}")
        finally:
            iso_obj.close()
    else:
        # iso is already an opened object
        for path in paths_to_try:
            for path_type in path_types:
                try:
                    with iso.open_file_from_iso(**{path_type: path}) as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_md5.update(chunk)
                        opened = True
                        break
                except Exception:
                    continue
            if opened:
                break
        if not opened:
            raise pycdlibexception.PyCdlibInvalidInput(f"Could not find path: {file_path}")

    return hash_md5.hexdigest()


def compute_hash_for_largest_files_in_iso(iso_path: str, n: int = 5) -> list[tuple[str, int, str]]:
    """Find the largest n files in an ISO archive and compute their MD5 hashes.

    Args:
        iso_path: Path to the ISO file
        n: Number of largest files to find

    Returns:
        List of tuples (file_path, file_size, md5_hash)
    """
    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.open(iso_path)

    try:
        file_sizes = []

        # Walk through all files in the ISO
        for dir_path, dir_entries, file_entries in iso.walk(iso_path="/"):
            for file_entry in file_entries:
                if file_entry in (".", ".."):
                    continue

                # Strip ISO 9660 version number (e.g., ";1") for consistent path matching
                normalized_id = file_entry.split(";")[0]

                # Ensure proper path joining with separator
                if dir_path.endswith("/"):
                    full_path = dir_path + normalized_id
                else:
                    full_path = dir_path + "/" + normalized_id

                # Get actual file size from the DirectoryRecord
                try:
                    iso_record_path = dir_path.rstrip("/") + "/" + file_entry
                    rec = iso.get_record(iso_path=iso_record_path)
                    file_size = rec.data_length
                except Exception:
                    file_size = 0
                file_sizes.append((full_path, file_size))

        # Sort by size descending and take the largest n files
        largest_files = sorted(file_sizes, key=lambda x: x[1], reverse=True)[:n]

        # Compute MD5 hashes for the largest files
        file_hashes = []
        for file_path, file_size in largest_files:
            file_hash = compute_md5_from_iso(iso, file_path)
            file_hashes.append((file_path, file_size, file_hash))

        return file_hashes

    finally:
        iso.close()


def list_files_in_iso(iso_path: str) -> list[str]:
    """List all files in an ISO archive.

    Args:
        iso_path: Path to the ISO file

    Returns:
        List of file paths within the ISO
    """
    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.open(iso_path)

    try:
        files = []
        for dir_path, dir_entries, file_entries in iso.walk(iso_path="/"):
            for file_entry in file_entries:
                # Handle both string entries and file entry objects
                if isinstance(file_entry, str):
                    if file_entry in (".", ".."):
                        continue
                    file_id = file_entry
                else:
                    if file_entry.file_identifier() in (b".", b".."):
                        continue
                    file_id = file_entry.file_identifier().decode("utf-8")

                # Strip ISO 9660 version number (e.g., ";1") for consistent path matching
                normalized_id = file_id.split(";")[0]

                # Ensure proper path joining with separator
                if dir_path.endswith("/"):
                    full_path = dir_path + normalized_id
                else:
                    full_path = dir_path + "/" + normalized_id
                files.append(full_path)
        return files
    finally:
        iso.close()


def list_executables_in_iso(iso_path: str) -> list[str]:
    """List all executable files (.exe, .bat, .com) in an ISO archive.

    Args:
        iso_path: Path to the ISO file

    Returns:
        List of executable file paths within the ISO
    """
    EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".com"}
    all_files = list_files_in_iso(iso_path)
    executables = []
    for f in all_files:
        if os.path.splitext(f)[1].lower() in EXECUTABLE_EXTENSIONS:
            executables.append(f)
    return executables


def get_iso_volume_label(iso_path: str) -> str | None:
    """Get the volume label from an ISO file.

    Args:
        iso_path: Path to the ISO file

    Returns:
        Volume label string, or None if not available
    """
    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.open(iso_path)

    try:
        pvd = iso.pvd
        if pvd:
            vol_id = pvd.volume_identifier.decode("ascii", errors="ignore").strip()
            if not vol_id:
                logger.warning("Empty volume identifier in ISO: %s", iso_path)
            return vol_id if vol_id else None
        logger.warning("No primary volume descriptor found in ISO: %s", iso_path)
        return None
    except Exception as e:
        logger.warning("Failed to read volume label from ISO %s: %s", iso_path, e)
        return None
    finally:
        iso.close()
