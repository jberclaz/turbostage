from PySide6.QtWidgets import QDialog


class ConfigureGameDialog(QDialog):
    def __init__(self, game_name: str, game_id: int):
        super().__init__()
        self._game_name = game_name
        self._game_id = game_id

        self.setWindowTitle("Configure game")
        self.setModal(True)
