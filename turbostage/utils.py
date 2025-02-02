import hashlib
import os.path
import platform
import re
import sqlite3
import subprocess
import zipfile
from collections import Counter
from datetime import datetime

from turbostage.igdb_client import IgdbClient


def epoch_to_formatted_date(epoch_s: int) -> str:
    dt = datetime.fromtimestamp(epoch_s)
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


def add_new_game_version(
    game_name: str,
    version_name: str,
    igdb_id: int,
    game_archive: str,
    binary: str,
    cpu_cycles: int,
    config: str,
    db_path: str,
    igdb_client,
):
    # 1. check if game exists in db
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = "SELECT count(*) FROM games WHERE igdb_id = ?"
    cursor.execute(query, (igdb_id,))
    count = cursor.fetchall()[0][0]
    if count > 0:
        cursor.execute("SELECT id FROM games WHERE igdb_id = ?", (igdb_id,))
        game_id = cursor.fetchall()[0][0]
    else:
        # 2.1 query IGDB for extra info
        details = fetch_game_details(igdb_client, igdb_id)
        # 2.2 add game entry in games table
        cursor.execute(
            """
            INSERT INTO games (title, summary, release_date, genre, publisher, igdb_id, cover_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                game_name,
                details["summary"],
                details["release_date"],
                details["genres"],
                details["publisher"],
                igdb_id,
                details["cover"],
            ),
        )
        game_id = cursor.lastrowid
    # 2.5 TODO: check that this version does not already exist.
    # 3. add game version in version table
    cursor.execute(
        """
        INSERT INTO versions (game_id, version, executable, archive, config, cycles)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (game_id, version_name, binary, os.path.basename(game_archive), config, cpu_cycles),
    )
    version_id = cursor.lastrowid
    # 4. add hashes
    hashes = compute_hash_for_largest_files_in_zip(game_archive, n=4)
    if not binary in [h[0] for h in hashes]:
        with zipfile.ZipFile(game_archive, "r") as zf:
            h = compute_md5_from_zip(zf, binary)
            hashes.append((binary, 0, h))
    for h in hashes:
        cursor.execute(
            """
                    INSERT INTO hashes (version_id, file_name, hash)
                    VALUES (?, ?, ?)""",
            (version_id, h[0], h[2]),
        )
    # 5. add local version
    cursor.execute(
        "INSERT INTO local_versions (version_id, archive) VALUES (?, ?)", (version_id, os.path.basename(game_archive))
    )
    conn.commit()
    conn.close()


def fetch_game_details(igdb_client, igdb_id) -> dict:
    result = igdb_client.query(
        "games", ["release_dates", "genres", "summary", "involved_companies", "cover"], f"id={igdb_id}"
    )
    details = result[0]

    response = igdb_client.query("genres", ["name"], f"id=({','.join([str(i) for i in details['genres']])})")
    assert len(response) == len(details["genres"])
    genres_string = ", ".join(r["name"] for r in response)

    dates_result = igdb_client.query(
        "release_dates",
        ["date"],
        f"platform={IgdbClient.DOS_PLATFORM_ID}&id=({','.join([str(d) for d in details['release_dates']])})",
    )
    release_epoch = dates_result[0]["date"]

    response = igdb_client.query(
        "involved_companies",
        ["company", "developer"],
        f"id=({','.join(str(i) for i in details['involved_companies'])})",
    )
    company_ids = set(r["company"] for r in response if r["developer"])
    if not company_ids:
        company_ids = set(r["company"] for r in response)
    if company_ids:
        response = igdb_client.query("companies", ["name"], f"id=({','.join(str(i) for i in company_ids)})")
        companies = ", ".join(r["name"] for r in response)
    else:
        companies = ""

    response = igdb_client.query("covers", ["url"], f"id={details['cover']}")
    assert len(response) == 1
    cover_info = response[0]

    return {
        "summary": details["summary"] if "summary" in details else "",
        "genres": genres_string,
        "release_date": release_epoch,
        "publisher": companies,
        "cover": cover_info["url"],
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
        output = subprocess.check_output([dosbox_exec, "-V"], text=True, shell=True)
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
