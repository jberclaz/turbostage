from PySide6.QtWidgets import QFileDialog


class LockedFileDialog(QFileDialog):
    """A QFileDialog that restricts navigation to its initial directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_path = self.directory().path()

        # 1. Use Qt's non-native dialog for customization
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # 2. Hide the sidebar with default locations (e.g., Desktop, Documents)
        self.setSidebarUrls([])

        # 3. Use the signal-slot mechanism as a fallback to prevent
        #    navigation via other means (e.g., manually editing the path).
        self.directoryEntered.connect(self.on_directory_entered)

    def on_directory_entered(self, path: str):
        if path != self.initial_path:
            self.setDirectory(self.initial_path)
