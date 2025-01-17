import hashlib
import os.path
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime

from turbostage import utils


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


def add_new_game_version(game_name: str, version_name: str, igdb_id: int, game_archive: str, binary: str, config: str,
                         db_path: str, igdb_client):
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
        result = igdb_client.query("games", ["release_dates", "genres"], f"id={igdb_id}")
        details = result[0]
        dates_result = igdb_client.query("release_dates", ["date"], f"platform=13&id=({",".join([str(d) for d in details['release_dates']])})")
        if len(dates_result) == 0:
            release_date = ""
        else:
            epoch = dates_result[0]["date"]
            date_time = datetime.utcfromtimestamp(epoch)
            release_date = date_time.year
        genre_result = igdb_client.query("genres", ["name"], f"id=({",".join([str(i) for i in details['genres']])})")
        genre_string = ", ".join(g["name"] for g in genre_result)
        # 2.2 add game entry in games table
        cursor.execute(
            """
            INSERT INTO games (title, release_year, genre, igdb_id)
            VALUES (?, ?, ?, ?)
        """,
            (game_name, release_date, genre_string, igdb_id),
        )
        game_id = cursor.lastrowid
    # 2.5 TODO: check that this version does not already exist.
    # 3. add game version in version table
    cursor.execute(
        """
        INSERT INTO versions (game_id, version, executable, archive, config)
        VALUES (?, ?, ?, ?, ?)
        """,
        (game_id, version_name, binary, os.path.basename(game_archive), config),
    )
    version_id = cursor.lastrowid
    # 4. add hashes
    hashes = utils.compute_hash_for_largest_files_in_zip(game_archive, n=4)
    if not binary in [h[0] for h in hashes]:
        with zipfile.ZipFile(game_archive, "r") as zf:
            h = utils.compute_md5_from_zip(zf, binary)
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

class CancellationFlag:
    def __init__(self):
        self.cancelled = False

    def __call__(self):
        return self.cancelled
