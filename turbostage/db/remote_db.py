import os
from datetime import datetime

from PySide6.QtWidgets import QMessageBox

from turbostage.db.game_database import GameDatabase


class RemoteDB:
    def __init__(self, db: GameDatabase):
        self._db = db

    def export_specific_versions(self, version_ids: list[int]):
        export = {"generated_at": datetime.now().isoformat(), "games": {}}
        data = self._db.get_all_local_version_for_export()
        for row in data:
            version_id, game_id, version, executable, config_executable, config, cycles, requires_install = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], bool(row[7])
            )
            if version_id not in version_ids:
                continue
            if game_id not in export["games"]:
                export["games"][game_id] = {"versions": {}}
            if version in export["games"][game_id]["versions"]:
                continue
            hashes = self._db.get_version_hashes(version_id)
            export["games"][game_id]["versions"][version] = {
                "executable": executable,
                "config_executable": config_executable,
                "config": config,
                "cycles": cycles,
                "requires_install": requires_install,
                "hashes": {os.path.basename(h[0]): h[1] for h in hashes},
            }
        return export

    @staticmethod
    def open_github_with_payload(parent_ui, json_payload: str):
        import webbrowser
        from urllib.parse import quote_plus

        body = quote_plus(json_payload)
        url = f"https://github.com/jberclaz/turbostage_data/issues/new?template=submit_game.yml&body={body}&title={quote_plus('Config update')}"
        webbrowser.open(url)

        # Copy to clipboard
        QMessageBox.information(
            parent_ui, "Ready!", "GitHub issue opened with configuration upload.\n" "Just press 'Create'."
        )
