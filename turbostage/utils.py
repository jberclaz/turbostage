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


def fetch_game_details_online(igdb_client, igdb_id) -> GameDetails:
    details = igdb_client.get_game_details(igdb_id)

    genres = igdb_client.get_genres(details["genres"])
    genres_string = ", ".join(genres)

    release_epoch = igdb_client.get_release_date(details["release_dates"])

    companies = igdb_client.get_companies(details["involved_companies"])
    companies_string = ", ".join(companies)

    cover_url = igdb_client.get_cover_url(details["cover"])
    return GameDetails(
        release_date=release_epoch,
        genre=genres_string,
        summary=details["summary"] if "summary" in details else "",
        publisher=companies_string,
        cover_url=cover_url,
        igdb_id=igdb_id,
    )


def get_dosbox_version(dosbox_exec: str) -> str:
    try:
        output = subprocess.check_output(f"{dosbox_exec} -V", text=True, shell=True)
    except subprocess.CalledProcessError as e:
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


class CancellationFlag:
    def __init__(self):
        self.cancelled = False

    def __call__(self):
        return self.cancelled
