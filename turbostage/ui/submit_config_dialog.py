from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout


class SubmitLocalConfigDialog(QDialog):
    """
    Dialog that lists all *local* game versions that differ from the global DB
    and lets the user pick which ones to submit.
    """

    # Emitted when the user clicks "Submit" – payload is a list of version_id ints
    configsSelected = Signal(list)

    def __init__(
        self,
        local_versions: List[tuple[int, str, str]],
        parent=None,
    ):
        """
        Parameters
        ----------
        local_versions
            List of (version_id, title, version_name) for games that have
            a local config (source='local' or locally-overridden fields).
        """
        super().__init__(parent)
        self.setWindowTitle("Submit Local Configurations")
        self.setModal(True)
        self.resize(560, 400)

        self._setup_ui()
        self._populate_list(local_versions)

    # --------------------------------------------------------------------- #
    # UI construction
    # --------------------------------------------------------------------- #
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ---- Explanation -------------------------------------------------
        expl = QLabel(
            "<b>Submit your local DOSBox-Staging configurations</b><br><br>"
            "Only <u>hashes</u> and <u>configuration settings</u> will be sent. "
            "No game files, no archive names, no personal data.<br>"
        )
        expl.setWordWrap(True)
        layout.addWidget(expl)

        # ---- List of games -----------------------------------------------
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet(
            """
    QListWidget::item { padding: 4px; }
    QListWidget::item:checked { font-weight: bold; }
"""
        )
        layout.addWidget(self.list_widget)

        # ---- Buttons ----------------------------------------------------
        btn_box = QDialogButtonBox()
        self.submit_btn = btn_box.addButton("Submit", QDialogButtonBox.AcceptRole)
        self.cancel_btn = btn_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self._on_submit)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # --------------------------------------------------------------------- #
    # List handling
    # --------------------------------------------------------------------- #
    def _populate_list(self, local_versions: List[tuple[int, str, str]]):
        self.list_widget.blockSignals(True)  # Prevent signals during setup
        self.list_widget.clear()

        for title, _, version_id, version_name in local_versions:
            item_text = f"{title} – {version_name}"
            list_item = QListWidgetItem(item_text)
            list_item.setFlags(list_item.flags() | Qt.ItemIsUserCheckable)
            list_item.setCheckState(Qt.Checked)
            list_item.setData(Qt.UserRole, version_id)

            self.list_widget.addItem(list_item)

        self.list_widget.blockSignals(False)

    def _on_submit(self):
        selected_ids: List[int] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_ids.append(item.data(Qt.UserRole))

        if not selected_ids:
            QMessageBox.information(self, "Nothing selected", "Please select at least one configuration.")
            return

        self.configsSelected.emit(selected_ids)
        self.accept()
