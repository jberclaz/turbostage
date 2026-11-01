# Agent Notes for TurboStage

## Project Overview
TurboStage is a user-friendly desktop frontend for DOSBox Staging, designed to simplify launching and managing DOS games. It provides an intuitive GUI for organizing game libraries, configuring emulator settings, and running classic DOS games with minimal setup.

## Technology Stack
- **Language**: Python 3.11+
- **GUI Framework**: PySide6 (Qt6 bindings)
- **Build Tool**: Poetry with poetry-dynamic-versioning
- **Packaging**: PyInstaller (single-file executable)
- **Testing**: unittest with xmlrunner
- **Code Quality**: Black, isort, pre-commit hooks

## Project Structure
```
turbostage/
├── turbostage/           # Main source code
│   ├── main.py           # Entry point
│   ├── ui/               # UI components (Qt widgets)
│   ├── db/               # Database management
│   ├── content/          # Static resources
│   └── ...
├── test/                 # Unit tests
├── doc/                  # Documentation/screenshots
├── build/                # Build artifacts
├── dist/                 # Distribution files
├── pyproject.toml        # Poetry configuration
├── Makefile              # Build automation
└── requirements*.txt     # Dependencies
```

## Development Setup

### Initial Setup
```bash
make init
```
This creates a virtual environment, installs dependencies, and sets up pre-commit hooks.

### Manual Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip3 install uv
uv pip install -r requirements-dev.txt
pre-commit install
```

### Game Metadata (IGDB snapshot)
The app never calls the IGDB API and ships no credentials. Game metadata
(titles, summaries, dates, genres, companies, ratings, image ids) for every DOS
game on IGDB is bundled in `turbostage/content/game_metadata.json.gz`, read by
`turbostage/game_metadata.py` for lookups and title search. Only images are
fetched at runtime, from IGDB's public image CDN (no credentials needed).

The snapshot is regenerated locally, never in CI, and committed:
```bash
IGDB_CLIENT_ID=... IGDB_CLIENT_SECRET=... python scripts/build_metadata_cache.py
```
The output is deterministic, so an unchanged IGDB produces an identical file.
The About dialog credits IGDB.com, as required when showing its data.

### Flatpak
`flatpak/` holds the Flatpak packaging (app id `io.github.jberclaz.turbostage`):
freedesktop runtime, PySide6 (with its own Qt) from PyPI wheels, and DOSBox
Staging built from source inside the package. The KDE runtime +
`io.qt.PySide.BaseApp` is deliberately not used: every Qt patch update of the
runtime breaks base-app apps until they are rebuilt. Inside the sandbox the app always uses the bundled
`/app/bin/dosbox` and hides the DOSBox download/browse buttons
(`utils.is_flatpak()`).
```bash
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak/build.sh                     # builds and installs a local user Flatpak
flatpak run io.github.jberclaz.turbostage
```
The manifest builds from the local checkout (`type: dir`); a Flathub
submission replaces that source with a git tag and commit.

### App Data Location
TurboStage keeps its files (library database, logs, `crash.log`, image cache,
downloaded DOSBox and ROMs, CD-ROM installs) in a `TurboStage` folder inside
the platform data folder: `~/.local/share/TurboStage`,
`~/Library/Application Support/TurboStage`, `%APPDATA%\TurboStage`. Always
build paths with `turbostage/app_paths.py`. Versions up to 0.13 used the data
folder itself; `turbostage/data_migration.py` moves those files at startup.

## Common Commands

### Run Application
```bash
source venv/bin/activate
python -m turbostage.main
# Or with poetry:
poetry run turbostage
```

### Run Tests
```bash
make test
# Or directly:
python -m xmlrunner discover -o test-reports -s test
```

### Build Package
```bash
make build
# Creates wheel/sdist in dist/
```

### Build Standalone Executable
```bash
make package
# Creates turbostage-linux-v{version}.zip
```

### Clean Build Artifacts
```bash
make clean
```

## Code Style
This project uses:
- **Black**: Code formatting (line length: 120)
- **isort**: Import sorting (black profile)
- **pre-commit**: Automated checks before commits

Configuration is in `.pre-commit-config.yaml` and `pyproject.toml`.

## Key Dependencies
- `pyside6==6.11.1` - Qt GUI framework
- `requests==2.32.3` - HTTP requests
- `pycdlib==1.14.0` - ISO 9660 image reading

## CI/CD
GitHub Actions workflows:
- **unit_tests.yml**: Runs on PR/push to master (Python 3.11, Ubuntu)
- **linux.yml**, **macos.yml**, **windows.yml**: Platform-specific builds

## Versioning
Uses `poetry-dynamic-versioning` for automatic versioning based on git tags.
Current version is defined in `turbostage/__init__.py`.

## Entry Points
- **Development**: `turbostage.main:main`
- **Installed**: `turbostage` command
- **Arguments**: `-s, --skip_splash` to skip splash screen
