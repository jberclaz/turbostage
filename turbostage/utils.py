import hashlib
import os.path
import platform
import re
import subprocess
import zipfile
from datetime import datetime, timezone

from turbostage.db.game_database import GameDetails


def epoch_to_formatted_date(epoch_s: int) -> str:
    dt = datetime.fromtimestamp(epoch_s, timezone.utc)
    return dt.strftime("%B %d, %Y")


def compute_md5_from_zip(zip_archive, file_name):
    """Compute the MD5 hash of a file inside a ZIP archive."""
    hash_md5 = hashlib.md5()
    with zip_archive.open(file_name, "r") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def compute_hash_for_largest_files_in_zip(zip_path, n=5):
    """Find the largest n files in a ZIP archive."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Get file info with sizes
        file_sizes = [(info.filename, info.file_size) for info in zf.infolist()]

        # Sort by size and take the largest n files
        largest_files = sorted(file_sizes, key=lambda x: x[1], reverse=True)[:n]

        # Compute MD5 hashes for the largest files
        file_hashes = [(file, size, compute_md5_from_zip(zf, file)) for file, size in largest_files]
    return file_hashes


EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".com"}


def hash_archive_top(game_path: str, n: int = 4) -> tuple[str, list[tuple[str, int, str]]]:
    """Hash the largest n files of a game archive for library matching.

    Returns (archive_type, hashes). Single choke point previously
    triplicated across the scanner, the Add dialog, and AddGameWorker.
    """
    from turbostage import iso_utils

    if iso_utils.is_iso_file(game_path):
        return "iso", iso_utils.compute_hash_for_largest_files_in_iso(game_path, n)
    return "zip", compute_hash_for_largest_files_in_zip(game_path, n)


def hash_archive_executables(game_path: str) -> list[tuple[str, int, str]]:
    """Hash all executables in a game archive for path resolution."""
    from turbostage import iso_utils

    if iso_utils.is_iso_file(game_path):
        return iso_utils.compute_hashes_for_executables_in_iso(game_path)
    return compute_hashes_for_executables_in_zip(game_path)


def hash_for_new_version(game_path: str, binary: str | None, n: int = 4) -> tuple[str, list[tuple[str, int, str]]]:
    """Hash an archive for a brand-new version, ensuring binary is covered."""
    import zipfile

    from turbostage import iso_utils

    archive_type, hashes = hash_archive_top(game_path, n)
    names = [h[0] for h in hashes]
    if binary and binary not in names:
        if archive_type == "iso":
            h = iso_utils.compute_md5_from_iso(game_path, binary)
        else:
            with zipfile.ZipFile(game_path, "r") as zf:
                h = compute_md5_from_zip(zf, binary)
        hashes.append((binary, 0, h))
    return archive_type, hashes


def compute_hashes_for_executables_in_zip(zip_path):
    """Compute MD5 hashes for all executable files (.exe, .bat, .com) in a ZIP archive."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        return [
            (info.filename, info.file_size, compute_md5_from_zip(zf, info.filename))
            for info in zf.infolist()
            if os.path.splitext(info.filename)[1].lower() in EXECUTABLE_EXTENSIONS
        ]


def fetch_game_details_online(igdb_client, igdb_id) -> GameDetails | None:
    details = igdb_client.get_game_info(igdb_id)
    if not details:
        return None
    genres = details.get("genres") or []
    genres_string = ", ".join(genres) if isinstance(genres, list) else str(genres)
    release_epoch = details.get("release_date")
    return GameDetails(
        title=None,
        release_date=release_epoch,
        genre=genres_string,
        summary=details.get("summary") or "",
        publisher=details.get("publisher") or "",
        cover_url=details.get("cover_url") or "",
        igdb_id=igdb_id,
        developer=details.get("developer") or "",
        screenshot_urls=details.get("screenshot_urls") or "[]",
        rating=details.get("rating"),
    )


def get_dosbox_version(dosbox_exec: str) -> str:
    if not dosbox_exec:
        return ""
    try:
        output = subprocess.check_output([dosbox_exec, "-V"], text=True, shell=False)
    except (subprocess.CalledProcessError, OSError) as e:
        return ""
    for line in output.splitlines():
        if "version" not in line:
            continue
        match = re.search(r"version ([0-9]+\.[0-9]+\.[0-9]+)", line)
        if match:
            version = match.group(1)
            return version
    return ""


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() == "true"
    raise RuntimeError(f"Cannot convert value {value} to bool")


def compute_file_md5(file_path: str) -> str:
    """Compute the MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Error computing hash for '{file_path}': {e}")
        return ""


def list_files_with_md5(folder: str) -> dict[str, str]:
    """
    Recursively list all files in a folder and compute their MD5 hashes.

    Args:
        folder (str): The path of the folder to scan.

    Returns:
        List[Tuple[str, str]]: A list of tuples where each tuple contains
                               the file path and its MD5 hash.
    """
    result = {}
    for root, _, files in os.walk(folder):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            md5_hash = compute_file_md5(file_path)
            result[file_path] = md5_hash
    return result


def get_os():
    return platform.system()


def prune_image_cache(folder: str, max_files: int = 500, max_bytes: int = 200 * 1024 * 1024) -> None:
    """Bound an on-disk image cache (covers/screenshots) with LRU eviction.

    Deletes oldest files (by mtime) until both limits hold. Best-effort:
    never raises — a cache must not break the library view.
    """
    try:
        entries = []
        total_bytes = 0
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            try:
                if not os.path.isfile(path):
                    continue
                stat = os.stat(path)
            except OSError:
                continue
            entries.append((stat.st_mtime, path, stat.st_size))
            total_bytes += stat.st_size
        if len(entries) <= max_files and total_bytes <= max_bytes:
            return
        entries.sort(key=lambda e: e[0])
        for _, path, size in entries:
            if len(entries) <= max_files and total_bytes <= max_bytes:
                break
            try:
                os.unlink(path)
            except OSError:
                continue
            total_bytes -= size
            entries.pop(0)
    except OSError:
        pass


class CancellationFlag:
    def __init__(self):
        self.cancelled = False

    def __call__(self):
        return self.cancelled
