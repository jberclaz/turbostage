from unittest import TestCase

from turbostage import utils


class TestUtils(TestCase):
    def test_add_new_game_version(self):
        name = "Mortal Kombat"
        version = "vga"
        game_id = 1234
        archive = "../games/mortal_kombat.zip"
        binary = "MK/MK.EXE"
        config = ""
        db_path = "/home/jrb/.local/share/turbostage.db"
        utils.add_new_game_version(name, version, game_id, archive, binary, config, db_path)