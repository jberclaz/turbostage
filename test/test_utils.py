import io
import os
import random
import sqlite3
import tempfile
import zipfile
from unittest import TestCase

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

    @staticmethod
    def create_mockup_archive(archive_path: str, filenames: list[str]) -> None:
        with zipfile.ZipFile(archive_path, "w") as zip_obj:
            for filename in filenames:
                with io.BytesIO() as in_memory_file:
                    file_size_bytes = random.randint(100, 1000)
                    in_memory_file.write(os.urandom(file_size_bytes))
                    in_memory_file.seek(0)  # Reset the file pointer to the beginning
                    zip_obj.writestr(filename, in_memory_file.read())
