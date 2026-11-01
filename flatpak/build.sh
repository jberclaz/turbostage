#!/usr/bin/env bash
# Build and install TurboStage as a local Flatpak (user installation).
#
# Requires: flatpak, flatpak-builder, and the Flathub remote.
#   flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
set -euo pipefail
cd "$(dirname "$0")"

APP_ID=io.github.jberclaz.turbostage
# Same shared-modules commit as flathub/io.github.dosbox-staging
SHARED_MODULES_COMMIT=6eed6448215ff322f3567f2fba53ea444f5861df

if [ ! -d shared-modules/.git ]; then
    git clone https://github.com/flathub/shared-modules.git shared-modules
fi
git -C shared-modules fetch --quiet origin
git -C shared-modules checkout --quiet "$SHARED_MODULES_COMMIT"

flatpak-builder --user --install --force-clean --install-deps-from=flathub \
    --repo=repo build-dir "$APP_ID.yml"

echo
echo "Run it with: flatpak run $APP_ID"
