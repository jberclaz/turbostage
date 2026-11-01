#!/bin/sh
# -P: don't put the current directory on sys.path, so a "turbostage" folder
# where the app is started from (e.g. a git checkout) can't shadow /app.
exec python3 -P -m turbostage.main "$@"
