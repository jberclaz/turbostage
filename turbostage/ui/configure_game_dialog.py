from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QVBoxLayout

from turbostage.ui.game_setup_widget import GameSetupWidget


class ConfigureGameDialog(QDialog):
    def __init__(
        self,
        game_archive: str,
    ):
        super().__init__()

        self.setWindowTitle("Configure game")
        self.setModal(True)

        self.layout = QVBoxLayout(self)

        self.version_label = QLabel("Version name")
        self.version_name = QLineEdit(self)
        self.version_name.setPlaceholderText("Eg: 'vga', 'en', '1.2', ...")
        self.version_name.textChanged.connect(self._on_settings_changed)
        self.layout.addWidget(self.version_label)
        self.layout.addWidget(self.version_name)

        self.config_widget = GameSetupWidget(auto_save_enable=False)
        self.config_widget.set_new_game(game_archive)
        self.config_widget.settings_applied.connect(self._on_add_game)
        self.config_widget.settings_changed.connect(self._on_settings_changed)
        self.layout.addWidget(self.config_widget)

    def _on_add_game(self):
        self.accept()

    def _on_settings_changed(self):
        if self.config_widget.selected_binary is None:
            self.config_widget.enable_button(False)
        else:
            self.config_widget.enable_button(True)

    @property
    def cpu_cycles(self) -> int:
        return self.config_widget.cpu_cycles

    @property
    def selected_binary(self) -> str:
        return self.config_widget.selected_binary

    @property
    def config_text(self) -> str:
        return self.config_widget.dosbox_config_text.toPlainText()

    @property
    def version(self):
        return self.version_name.text() if self.version_name.text() else "default"
