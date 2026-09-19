"""ISO utility functions for TurboStage.

This module provides utility functions for working with ISO 9660 image files,
including computing MD5 hashes, listing files, and extracting metadata.
"""

import hashlib
import logging
import os
from contextlib import contextmanager

import pycdlib
from pycdlib import pycdlibexception

logger = logging.getLogger(__name__)

EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".com"}
_ISO_PATH_TYPES = ("iso_path", "joliet_path", "rr_path")


@contextmanager
def _open_iso(iso_path: str):
    """Open an ISO, guaranteeing close (replaces 5 duplicated open/finally blocks)."""
    iso = pycdlib.PyCdlib()
    iso.open(iso_path)
    try:
        yield iso
    finally:
        iso.close()


def _iter_iso_files(iso) -> list[tuple[str, str]]:
    """Yield (normalized_path, raw_entry_id) for every file in an open ISO."""
    for dir_path, _dir_entries, file_entries in iso.walk(iso_path="/"):
        for file_entry in file_entries:
            if isinstance(file_entry, str):
                if file_entry in (".", ".."):
                    continue
                file_id = file_entry
            else:
                if file_entry.file_identifier() in (b".", b".."):
                    continue
                file_id = file_entry.file_identifier().decode("utf-8", errors="ignore")
            normalized_id = file_id.split(";")[0]
            full_path = dir_path + normalized_id if dir_path.endswith("/") else dir_path + "/" + normalized_id
            yield full_path, file_id


def _read_iso_entry(iso, file_path: str):
    """Open a file inside an ISO, trying path types and ;1 suffix variants."""
    paths_to_try = [file_path] if ";" in file_path else [file_path, file_path + ";1"]
    last_error = None
    for path in paths_to_try:
        for path_type in _ISO_PATH_TYPES:
            try:
                return iso.open_file_from_iso(**{path_type: path})
            except Exception as e:  # noqa: BLE001 - probe next spelling on any miss
                last_error = e
                continue
    raise pycdlibexception.PyCdlibInvalidInput(f"Could not find path: {file_path}") from last_error


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
    hash_md5 = hashlib.md5()

    def _hash_open(iso_obj) -> None:
        with _read_iso_entry(iso_obj, file_path) as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

    if isinstance(iso, str):
        with _open_iso(iso) as iso_obj:
            _hash_open(iso_obj)
    else:
        _hash_open(iso)

    return hash_md5.hexdigest()


def compute_hash_for_largest_files_in_iso(iso_path: str, n: int = 5) -> list[tuple[str, int, str]]:
    """Find the largest n files in an ISO archive and compute their MD5 hashes.

    Args:
        iso_path: Path to the ISO file
        n: Number of largest files to find

    Returns:
        List of tuples (file_path, file_size, md5_hash)
    """
    with _open_iso(iso_path) as iso:
        file_sizes = []

        for dir_path, _dir_entries, file_entries in iso.walk(iso_path="/"):
            for file_entry in file_entries:
                raw_id = (
                    file_entry
                    if isinstance(file_entry, str)
                    else file_entry.file_identifier().decode("utf-8", errors="ignore")
                )
                if raw_id in (".", ".."):
                    continue
                normalized_id = raw_id.split(";")[0]
                full_path = dir_path + normalized_id if dir_path.endswith("/") else dir_path + "/" + normalized_id
                # Get actual file size from the DirectoryRecord (advisory:
                # only ranks largest-N, so a miss degrades to 0).
                try:
                    rec = iso.get_record(iso_path=dir_path.rstrip("/") + "/" + raw_id)
                    file_size = rec.data_length
                except Exception:
                    file_size = 0
                file_sizes.append((full_path, file_size))

        # Sort by size descending and take the largest n files
        largest_files = sorted(file_sizes, key=lambda x: x[1], reverse=True)[:n]

        # Compute MD5 hashes for the largest files
        return [(file_path, file_size, compute_md5_from_iso(iso, file_path)) for file_path, file_size in largest_files]


def list_files_in_iso(iso_path: str) -> list[str]:
    """List all files in an ISO archive.

    Args:
        iso_path: Path to the ISO file

    Returns:
        List of file paths within the ISO
    """
    with _open_iso(iso_path) as iso:
        return [full_path for full_path, _raw in _iter_iso_files(iso)]


def list_executables_in_iso(iso_path: str) -> list[str]:
    """List all executable files (.exe, .bat, .com) in an ISO archive.

    Args:
        iso_path: Path to the ISO file

    Returns:
        List of executable file paths within the ISO
    """
    return [f for f in list_files_in_iso(iso_path) if os.path.splitext(f)[1].lower() in EXECUTABLE_EXTENSIONS]


def compute_hashes_for_executables_in_iso(iso_path: str) -> list[tuple[str, int, str]]:
    """Compute MD5 hashes for all executable files (.exe, .bat, .com) in an ISO archive."""
    executables = list_executables_in_iso(iso_path)
    with _open_iso(iso_path) as iso:
        return [(path, 0, compute_md5_from_iso(iso, path)) for path in executables]


def get_iso_volume_label(iso_path: str) -> str | None:
    """Get the volume label from an ISO file.

    Args:
        iso_path: Path to the ISO file

    Returns:
        Volume label string, or None if not available
    """
    try:
        with _open_iso(iso_path) as iso:
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
