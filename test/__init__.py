"""Keep the test suite away from the user's real TurboStage data and settings.

Tests build real widgets and run the real launcher, which write the library,
caches and logs to the app's data folder and read/write its settings. Run
the suite as a package (``make test``, i.e. ``discover -s test -t .``) so this
module runs first and redirects both.
"""

import atexit
import shutil
import tempfile

from PySide6.QtCore import QSettings, QStandardPaths

# Data folders (library, logs, caches, downloads): Qt's test location (~/.qttest).
QStandardPaths.setTestModeEnabled(True)

# Settings: a throwaway folder, removed when the run ends.
_settings_dir = tempfile.mkdtemp(prefix="turbostage-test-settings-")
for _format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
    QSettings.setPath(_format, QSettings.Scope.UserScope, _settings_dir)
atexit.register(shutil.rmtree, _settings_dir, ignore_errors=True)
