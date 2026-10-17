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

### IGDB Credentials
The IGDB (Twitch) app credentials are not in the repository. Without them the
app runs normally but treats IGDB as unreachable (no game search/metadata).
- **Development**: export `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET`.
- **Release builds**: CI runs `scripts/write_igdb_credentials.py` with the
  `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` GitHub Actions secrets, generating the
  gitignored `turbostage/_igdb_credentials.py` that PyInstaller bundles. For a
  local `make package`, run that script first.

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
