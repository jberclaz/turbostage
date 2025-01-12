import hashlib
import sqlite3
import zipfile
from collections import Counter


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

class CancellationFlag:
    def __init__(self):
        self.cancelled = False

    def __call__(self):
        return self.cancelled