# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['mangabackuputil_cli.py'],
    pathex=['.', 'proto'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'schema_mihon_pb2',
        'windnd',
        'convert_tachimanga_to_mihon',
        'convert_mihon_to_tachimanga',
        'manga_converter_engine',
        'manga_backup_converter_gui',
        'sqlite3',
        'plistlib',
        'zipfile',
        'gzip',
        'json',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mangabackuputil',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
