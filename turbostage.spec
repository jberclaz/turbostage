# -*- mode: python ; coding: utf-8 -*-


SYSTEM_LIBS_TO_EXCLUDE = {
    "libglib-2.0.so.0",
    "libgio-2.0.so.0",
    "libgobject-2.0.so.0",
    "libgmodule-2.0.so.0",
    "libgthread-2.0.so.0",
    "libgtk-3.so.0",
    "libgdk-3.so.0",
    "libgdk_pixbuf-2.0.so.0",
}

a = Analysis(
    ['turbostage/main.py'],
    pathex=[],
    binaries=[],
    datas=[('turbostage/content', 'turbostage/content'),
            ('turbostage/conf', 'turbostage/conf')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

a.binaries = [(name, path, typ) for name, path, typ in a.binaries
              if name not in SYSTEM_LIBS_TO_EXCLUDE]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='turbostage',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
