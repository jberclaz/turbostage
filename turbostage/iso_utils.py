"""ISO utility functions for TurboStage.

This module provides utility functions for working with ISO 9660 image files,
including computing MD5 hashes, listing files, and extracting metadata.
"""

import hashlib
import os
from typing import BinaryIO

import pycdlib
from pycdlib import pycdlibexception


def is_iso_file(file_path: str) -> bool:
    """Check if a file is an ISO image based on its extension.

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file has a .iso extension (case-insensitive)
    """
    return os.path.splitext(file_path)[1].lower() == ".iso"


def get_archive_type(file_path: str) -> str:
    """Determine the archive type based on file extension.

    Args:
        file_path: Path to the archive file

    Returns:
        'iso' if the file is an ISO image, 'zip' otherwise
    """
    return "iso" if is_iso_file(file_path) else "zip"


def _get_iso_file_content(iso, iso_path: str) -> bytes:
    """Extract file content from an ISO image.

    Args:
        iso: Opened pycdlib Iso object
        iso_path: Path to the file within the ISO

    Returns:
        File content as bytes
    """
    # pycdlib requires paths in the format /path/to/file
    if not iso_path.startswith("/"):
        iso_path = "/" + iso_path

    # Get file size by listing the file entry
    file_entry = None
    for child in iso.list_children(iso_path=iso_path):
        if child.file_identifier() == b"." or child.file_identifier() == b"..":
            continue
        # We need to find the actual file entry - for now just get content
        break

    # Read the file content
    content = bytearray()
    with iso.open_file_from_iso(iso_path=iso_path) as file_handle:
        while True:
            chunk = file_handle.read(65536)
            if not chunk:
                break
            content.extend(chunk)

    return bytes(content)


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
    opened = False

    if isinstance(iso, str):
        # iso is a path, open it
        iso_obj = pycdlib.PyCdlib()
        iso_obj.open(iso)
        try:
            for path_type in path_types:
                try:
                    with iso_obj.open_file_from_iso(**{path_type: file_path}) as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_md5.update(chunk)
                        opened = True
                        break
                except Exception:
                    continue
            if not opened:
                raise pycdlibexception.PyCdlibInvalidInput(f"Could not find path: {file_path}")
        finally:
            iso_obj.close()
    else:
        # iso is already an opened object
        for path_type in path_types:
            try:
                with iso.open_file_from_iso(**{path_type: file_path}) as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                    opened = True
                    break
            except Exception:
                continue
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
                # Handle both string entries and file entry objects
                if isinstance(file_entry, str):
                    if file_entry in (".", ".."):
                        continue
                    file_id = file_entry
                else:
                    if file_entry.file_identifier() in (b".", b".."):
                        continue
                    file_id = file_entry.file_identifier().decode("utf-8")

                # Ensure proper path joining with separator
                if dir_path.endswith("/"):
                    full_path = dir_path + file_id
                else:
                    full_path = dir_path + "/" + file_id

                if isinstance(file_entry, str):
                    file_size = 0
                else:
                    file_size = file_entry.get_data_length()
                file_sizes.append((full_path, file_size))

        # Sort by size and take the largest n files (filter out size 0)
        largest_files = sorted([f for f in file_sizes if f[1] > 0], key=lambda x: x[1], reverse=True)[:n]

        # If no files with size found, try getting any files
        if not largest_files and file_sizes:
            largest_files = file_sizes[:n]

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

                # Ensure proper path joining with separator
                if dir_path.endswith("/"):
                    full_path = dir_path + file_id
                else:
                    full_path = dir_path + "/" + file_id
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
        # Strip ISO 9660 version number (e.g., ";1") before checking extension
        base_name = f.split(";")[0]
        if os.path.splitext(base_name)[1].lower() in EXECUTABLE_EXTENSIONS:
            executables.append(base_name)
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
        # Try to get the volume identifier from the primary volume descriptor
        # The volume identifier is at a fixed offset in the primary volume descriptor
        # This is a simplified approach - pycdlib may have a better method
        pvd = iso.pvd
        if pvd:
            # Volume identifier is typically at offset 40, 32 bytes
            vol_id = pvd.volume_identifier.decode("ascii", errors="ignore").strip()
            return vol_id if vol_id else None
        return None
    finally:
        iso.close()
