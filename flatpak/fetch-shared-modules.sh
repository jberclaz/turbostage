#!/usr/bin/env bash
# Check out flathub/shared-modules (FluidSynth, SDL2_image recipes) at the
# commit flathub/io.github.dosbox-staging uses. Shared by build.sh and CI.
set -euo pipefail
cd "$(dirname "$0")"

SHARED_MODULES_COMMIT=6eed6448215ff322f3567f2fba53ea444f5861df

if [ ! -d shared-modules/.git ]; then
    git clone --quiet https://github.com/flathub/shared-modules.git shared-modules
fi
git -C shared-modules fetch --quiet origin
git -C shared-modules checkout --quiet "$SHARED_MODULES_COMMIT"
