from enum import IntEnum

MT32_ROMS_DOWNLOAD_URL = (
    "https://archive.org/download/mame-versioned-roland-mt-32-and-cm-32l-rom-files/MT32_v1.07_legacy_ROM_files.zip"
)
DOSBOX_STAGING_LINUX = "https://github.com/dosbox-staging/dosbox-staging/releases/download/v0.82.0/dosbox-staging-linux-x86_64-v0.82.0.tar.xz"
DOSBOX_STAGING_WINDOWS = (
    "https://github.com/dosbox-staging/dosbox-staging/releases/download/v0.82.0/dosbox-staging-windows-x64-v0.82.0.zip"
)

SUPPORTED_DOSBOX_VERSION = "0.82.0"

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
