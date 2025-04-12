from enum import IntEnum

SUPPORTED_DOSBOX_VERSION = "0.82.1"

MT32_ROMS_DOWNLOAD_URL = (
    "https://archive.org/download/mame-versioned-roland-mt-32-and-cm-32l-rom-files/MT32_v1.07_legacy_ROM_files.zip"
)
DOSBOX_STAGING_LINUX = f"https://github.com/dosbox-staging/dosbox-staging/releases/download/v{SUPPORTED_DOSBOX_VERSION}/dosbox-staging-linux-x86_64-v{SUPPORTED_DOSBOX_VERSION}.tar.xz"
DOSBOX_STAGING_WINDOWS = f"https://github.com/dosbox-staging/dosbox-staging/releases/download/v{SUPPORTED_DOSBOX_VERSION}/dosbox-staging-windows-x64-v{SUPPORTED_DOSBOX_VERSION}.zip"

CPU_CYCLES = {
    "Auto": 0,
    "8088 (4.77 MHz)": 300,
    "286-8": 700,
    "286-12": 1500,
    "386SX-20": 3000,
    "386DX-33": 6000,
    "386DX-40": 8000,
    "486DX-33": 12000,
    "486DX/2-66": 25000,
    "Pentium 90": 50000,
    "Pentium MMX-166": 100000,
    "Pentium II 300": 200000,
}


class FileType(IntEnum):
    CONFIG = 1
    SAVEGAME = 2
