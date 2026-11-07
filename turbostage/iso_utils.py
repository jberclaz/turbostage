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
_plain_reader_paths: set[str] = set()


@contextmanager
def _open_iso(iso_path: str):
    """Open an ISO, guaranteeing close (replaces 5 duplicated open/finally blocks).

    Images that pycdlib rejects as invalid are read with _PlainIso9660 instead.
    """
    try:
        iso = pycdlib.PyCdlib()
        iso.open(iso_path)
    except pycdlibexception.PyCdlibInvalidISO as e:
        if iso_path not in _plain_reader_paths:  # an image is opened many times; say it once
            _plain_reader_paths.add(iso_path)
            logger.warning("pycdlib cannot read '%s' (%s); using the basic ISO 9660 reader", iso_path, e)
        iso = _PlainIso9660(iso_path)
    try:
        yield iso
    finally:
        iso.close()


class _PlainIso9660:
    """Minimal read-only ISO 9660 reader, for images pycdlib rejects.

    pycdlib refuses directory records that carry an extended attribute record
    (written by some 1990s mastering tools, together with the protection flag)
    because it cannot skip them. Per ECMA-119, the data of such a file or
    directory starts xattr_len blocks into its extent.

    Implements only the subset of the pycdlib API this module uses: walk,
    get_record, open_file_from_iso (iso_path only), pvd and close. It reads the
    primary volume, so names match what pycdlib would report for plain images.
    """

    _MAX_DIRECTORIES = 10_000  # guards against loops in a corrupt directory tree

    def __init__(self, iso_path: str):
        self._file = open(iso_path, "rb")
        try:
            self._load()
        except Exception:
            self._file.close()
            raise

    def _read(self, offset: int, size: int) -> bytes:
        self._file.seek(offset)
        return self._file.read(size)

    def _load(self) -> None:
        sector = 16
        while True:
            descriptor = self._read(sector * 2048, 2048)
            if len(descriptor) < 2048 or descriptor[1:6] != b"CD001" or descriptor[0] == 255:
                raise pycdlibexception.PyCdlibInvalidISO("No primary volume descriptor")
            if descriptor[0] == 1:
                break
            sector += 1
        self._block_size = int.from_bytes(descriptor[128:130], "little") or 2048
        self.pvd = _PlainVolumeDescriptor(descriptor[40:72])

        self._directories: list[tuple[str, list[str], list[str]]] = []
        self._files: dict[str, tuple[int, int]] = {}  # path -> (byte offset, size)
        root = self._parse_record(descriptor[156:190])
        pending = [("/", root)]
        visited = set()
        while pending and len(self._directories) < self._MAX_DIRECTORIES:
            path, (_name, start, size, _is_dir) = pending.pop(0)
            if start in visited:
                continue
            visited.add(start)
            dir_names, file_names = [], []
            for name, child_start, child_size, is_dir in self._directory_entries(start, size):
                child_path = path.rstrip("/") + "/" + name
                if is_dir:
                    dir_names.append(name)
                    pending.append((child_path, (name, child_start, child_size, True)))
                else:
                    file_names.append(name)
                    self._files[child_path] = (child_start, child_size)
            self._directories.append((path, dir_names, file_names))

    def _parse_record(self, record: bytes):
        """Return (name, data offset, data size, is_dir) of a directory record."""
        xattr_len = record[1]
        extent = int.from_bytes(record[2:6], "little")
        size = int.from_bytes(record[10:14], "little")
        name = record[33 : 33 + record[32]].decode("ascii", errors="ignore")
        return name, (extent + xattr_len) * self._block_size, size, bool(record[25] & 0x02)

    def _directory_entries(self, start: int, size: int):
        data = self._read(start, size)
        offset = 0
        while offset < len(data):
            length = data[offset]
            if length < 34:  # 0 pads to the next sector; records never cross one
                offset = (offset // 2048 + 1) * 2048
                continue
            record = data[offset : offset + length]
            offset += length
            if len(record) < 34 or record[32] == 0 or record[33 : 33 + record[32]] in (b"\x00", b"\x01"):
                continue  # "." and ".."
            yield self._parse_record(record)

    def walk(self, iso_path: str = "/"):
        yield from self._directories

    def get_record(self, iso_path: str):
        return _PlainRecord(self._files[iso_path][1])

    def open_file_from_iso(self, iso_path: str):
        start, size = self._files[iso_path]
        return _PlainFileReader(self, start, size)

    def close(self) -> None:
        self._file.close()


class _PlainVolumeDescriptor:
    def __init__(self, volume_identifier: bytes):
        self.volume_identifier = volume_identifier


class _PlainRecord:
    def __init__(self, data_length: int):
        self.data_length = data_length


class _PlainFileReader:
    """File-like view of one file inside a _PlainIso9660 image."""

    def __init__(self, iso: _PlainIso9660, start: int, size: int):
        self._iso = iso
        self._position = start
        self._remaining = size

    def read(self, size: int = -1) -> bytes:
        if size < 0 or size > self._remaining:
            size = self._remaining
        data = self._iso._read(self._position, size)
        self._position += len(data)
        self._remaining -= len(data)
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


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
        'dir' for an unpacked game folder, 'iso' if the file is an ISO image,
        'zip' otherwise
    """
    if os.path.isdir(file_path):
        return "dir"
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
