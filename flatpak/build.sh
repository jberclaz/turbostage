#!/usr/bin/env bash
# Build and install TurboStage as a local Flatpak (user installation).
#
# Requires: flatpak, flatpak-builder, and the Flathub remote.
#   flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
set -euo pipefail
cd "$(dirname "$0")"

APP_ID=io.github.jberclaz.turbostage

./fetch-shared-modules.sh

flatpak-builder --user --install --force-clean --install-deps-from=flathub \
    --repo=repo build-dir "$APP_ID.yml"

echo
echo "Run it with: flatpak run $APP_ID"
