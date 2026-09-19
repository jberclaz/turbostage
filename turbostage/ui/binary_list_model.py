"""Shared list model for picking executables from an archive or folder."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class BinaryListModel(QAbstractListModel):
    def __init__(self, binaries=None):
        super().__init__()
        self.binaries = binaries or []

    def rowCount(self, parent=QModelIndex()):
        return len(self.binaries)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.binaries[index.row()]

    def set_binaries(self, binaries):
        self.beginResetModel()
        self.binaries = binaries
        self.endResetModel()
