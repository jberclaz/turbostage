import hashlib
import os.path
import platform
import re
import sqlite3
import subprocess
import zipfile
from collections import Counter
from datetime import datetime, timezone

from turbostage.igdb_client import IgdbClient


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


def find_game_for_hashes(hash_list: list[str], db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    placeholders = ", ".join("?" for _ in hash_list)
    query = f"SELECT version_id, hash FROM hashes WHERE hash IN ({placeholders})"
    cursor.execute(query, hash_list)
    matches = cursor.fetchall()
    conn.close()

    if len(matches) == 0:
        return None

    versions = [version for version, _ in matches]
    version_counts = Counter(versions)
    num_versions = len(version_counts)
    if num_versions == 1:
        return versions[0]
    # Find the most common version
    most_common_version, _ = version_counts.most_common(1)[0]
    return most_common_version


def fetch_game_details(igdb_client, igdb_id) -> dict:
    details = igdb_client.get_game_details(igdb_id)

    genres = igdb_client.get_genres(details["genres"])
    genres_string = ", ".join(genres)

    release_epoch = igdb_client.get_release_date(details["release_dates"])

    companies = igdb_client.get_companies(details["involved_companies"])
    companies_string = ", ".join(companies)

    cover_url = igdb_client.get_cover_url(details["cover"])
    return {
        "summary": details["summary"] if "summary" in details else "",
        "genres": genres_string,
        "release_date": release_epoch,
        "publisher": companies_string,
        "cover": cover_url,
    }


def update_version_info(version_id: int, version_name: str | None, binary: str, config: str, cycles: int, db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if version_name is not None:
        cursor.execute(
            """
                UPDATE versions SET version = ?, executable = ?, config = ?, cycles = ?
                WHERE id = ?
            """,
            (version_name, binary, config, cycles, version_id),
        )
    else:
        cursor.execute(
            """
                UPDATE versions SET executable = ?, config = ?, cycles = ?
                WHERE id = ?
            """,
            (binary, config, cycles, version_id),
        )
    conn.commit()
    conn.close()


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


def delete_local_game(game_id: int, db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
            DELETE FROM local_versions
            WHERE version_id in (
              SELECT id
              FROM versions
              WHERE game_id in (
                SELECT id
                FROM games
                WHERE igdb_id = ?
              )
            )
        """,
        (game_id,),
    )
    conn.commit()
    conn.close()


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


def add_extra_files(config_files: dict[str, bytes], version_id: int, file_type: int, db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM config_files WHERE version_id = ? AND type = ?", (version_id, file_type))
    for file_name, content in config_files.items():
        cursor.execute(
            """
                    INSERT INTO config_files(version_id, path, content, type)
                    VALUES (?, ?, ?, ?)
                    """,
            (version_id, file_name, content, file_type),
        )
    conn.commit()
    conn.close()


def get_os():
    return platform.system()


class CancellationFlag:
    def __init__(self):
        self.cancelled = False

    def __call__(self):
        return self.cancelled
