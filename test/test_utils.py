import hashlib
import io
import os
import random
import sqlite3
import tempfile
import zipfile
from unittest import TestCase
from unittest.mock import patch

from turbostage import utils
from turbostage.db.populate_db import initialize_database
from turbostage.igdb_client import IgdbClient


class TestUtils(TestCase):
    def test_add_new_game_version(self):
        name = "Mortal Kombat"
        version = "vga"
        game_id = 1618
        client = IgdbClient()
        with tempfile.TemporaryDirectory() as tempdir:
            archive_path = os.path.join(tempdir, f"mortal_kombat.zip")
            filenames = ["MK/MK.EXE", "MK/GAME.DAT", "MK/SOUND.DAT", "MK/START.BAT"]
            self.create_mockup_archive(archive_path, filenames)
            binary = "MK/MK.EXE"
            config = "[sdl]\nfull_screen = True\n"
            db_path = os.path.join(tempdir, "test.db")
            cpu_cycles = 12000
            initialize_database(db_path)
            utils.add_new_game_version(
                name, version, game_id, archive_path, binary, cpu_cycles, config, db_path, client
            )

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM games")
            results = cursor.fetchall()
            self.assertEqual(1, results[0][0])
            cursor.execute("SELECT count(*) FROM versions")
            results = cursor.fetchall()
            self.assertEqual(1, results[0][0])

    def test_epoch_to_formatted_date(self):
        self.assertEqual(utils.epoch_to_formatted_date(0), "January 01, 1970")
        self.assertEqual(utils.epoch_to_formatted_date(1672531200), "January 01, 2023")

    def test_compute_md5_from_zip(self):
        data = b"test data"
        expected_hash = hashlib.md5(data).hexdigest()

        file_name = "test.txt"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(file_name, data)

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            result = utils.compute_md5_from_zip(zf, file_name)
            self.assertEqual(result, expected_hash)

    def test_compute_hash_for_largest_files_in_zip(self):
        with tempfile.NamedTemporaryFile(suffix=".zip") as temp_file:
            with zipfile.ZipFile(temp_file.name, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("file1.txt", "A" * 1000)
                zf.writestr("file2.txt", "B" * 500)

            result = utils.compute_hash_for_largest_files_in_zip(temp_file.name, n=1)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0][0], "file1.txt")

    def test_find_game_for_hashes(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as temp_file:
            conn = sqlite3.connect(temp_file.name)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE hashes (version_id INTEGER, hash TEXT)")
            cursor.execute(
                "INSERT INTO hashes(version_id, hash) VALUES (1, 'abc123'), (1, 'cde234'), (1, 'def456'), (2, 'cde234'), (2, 'fgh789')"
            )
            conn.commit()
            conn.close()

            result = utils.find_game_for_hashes(["abc123"], temp_file.name)
            self.assertEqual(result, 1)

            result = utils.find_game_for_hashes(["cde234", "fgh789"], temp_file.name)
            self.assertEqual(result, 2)

            result = utils.find_game_for_hashes(["dklfj"], temp_file.name)
            self.assertEqual(result, None)

    def test_to_bool(self):
        self.assertTrue(utils.to_bool(True))
        self.assertTrue(utils.to_bool(1))
        self.assertTrue(utils.to_bool("true"))
        self.assertFalse(utils.to_bool(False))
        self.assertFalse(utils.to_bool(0))
        self.assertFalse(utils.to_bool("false"))
        with self.assertRaises(RuntimeError):
            utils.to_bool([])

    @patch("subprocess.check_output", return_value="First line\nDOSBox version 0.74.1\n")
    def test_get_dosbox_version(self, mock_subprocess):
        result = utils.get_dosbox_version("dosbox")
        self.assertEqual(result, "0.74.1")

    def test_compute_file_md5(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="wb") as temp_file:
            temp_file.write(b"test")
            temp_file.flush()

            expected_hash = hashlib.md5(b"test").hexdigest()
            result = utils.compute_file_md5(temp_file.name)
            self.assertEqual(result, expected_hash)

    def test_list_files_with_md5(self):
        mock_files = {"/fake_dir/file1.txt": "md5hash1", "/fake_dir/file2.txt": "md5hash2"}

        with patch("os.walk", return_value=[("/fake_dir", [], ["file1.txt", "file2.txt"])]):
            with patch("turbostage.utils.compute_file_md5", side_effect=lambda x: mock_files[x]):
                result = utils.list_files_with_md5("/fake_dir")
                self.assertEqual(result, mock_files)

    @staticmethod
    def create_mockup_archive(archive_path: str, filenames: list[str]) -> None:
        with zipfile.ZipFile(archive_path, "w") as zip_obj:
            for filename in filenames:
                with io.BytesIO() as in_memory_file:
                    file_size_bytes = random.randint(100, 1000)
                    in_memory_file.write(os.urandom(file_size_bytes))
                    in_memory_file.seek(0)  # Reset the file pointer to the beginning
                    zip_obj.writestr(filename, in_memory_file.read())
