import os

from PySide6.QtWidgets import QFileDialog


class LockedFileDialog(QFileDialog):
    """A QFileDialog that restricts navigation to its initial directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_path = os.path.realpath(self.directory().path())

        # 1. Use Qt's non-native dialog for customization
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # 2. Hide the sidebar with default locations (e.g., Desktop, Documents)
        self.setSidebarUrls([])

        # 3. Use the signal-slot mechanism as a fallback to prevent
        #    navigation via other means (e.g., manually editing the path).
        self.directoryEntered.connect(self.on_directory_entered)

    def on_directory_entered(self, path: str):
        if os.path.realpath(path) != self.initial_path:
            self.setDirectory(self.initial_path)

    def selectedFiles(self):
        """Only return files inside the initial directory (symlink-aware)."""
        files = super().selectedFiles()
        return [
            f
            for f in files
            if os.path.realpath(os.path.dirname(f) or ".") == self.initial_path
            or os.path.realpath(f).startswith(self.initial_path + os.sep)
        ]

    def accept(self):
        # Re-validate on accept: covers typed paths and symlink escapes that
        # bypass directoryEntered.
        files = super().selectedFiles()
        if files:
            for f in files:
                # Resolve symlinks; the target must stay inside the lock dir.
                real = os.path.realpath(f)
                parent = os.path.realpath(os.path.dirname(f) or ".")
                if parent != self.initial_path and not real.startswith(
                    self.initial_path + os.sep
                ):
                    self.setDirectory(self.initial_path)
                    return
        super().accept()
