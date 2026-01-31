# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for MindScribe Desktop.

Build command:
    pyinstaller MindScribe.spec --clean

Output:
    dist/MindScribe/MindScribe.exe
"""

import sys
import platform
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect PortAudio DLLs bundled with sounddevice
sounddevice_data = collect_data_files('_sounddevice_data')

# Collect plyer platform backends (lazy-loaded)
if platform.system() == "Darwin":
    plyer_imports = collect_submodules('plyer.platforms.macosx')
else:
    plyer_imports = collect_submodules('plyer.platforms.win')

# Platform-specific hidden imports
if platform.system() == "Darwin":
    _platform_imports = [
        'plyer.platforms.macosx',
        'plyer.platforms.macosx.notification',
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        'pystray._darwin',
    ]
else:
    _platform_imports = [
        'plyer.platforms.win',
        'plyer.platforms.win.notification',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pystray._win32',
    ]

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=sounddevice_data,
    hiddenimports=_platform_imports + [
        # App modules (PyInstaller may miss dynamic imports)
        'src',
        'src.app',
        'src.config',
        'src.config.settings',
        'src.config.dotenv_loader',
        'src.core',
        'src.core.audio_recorder',
        'src.core.chunker',
        'src.core.hotkey_manager',
        'src.core.text_inserter',
        'src.core.transcriber',
        'src.ui',
        'src.ui.icons',
        'src.ui.notification',
        'src.ui.overlay',
        'src.ui.settings_window',
        'src.ui.tray_icon',
        # audioop replacement for Python 3.13+
        'audioop_lts',
        'audioop',
    ] + plyer_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev-only packages
        'pytest',
        'pytest_cov',
        'customtkinter',
        # Unused numpy sub-packages (saves ~30MB)
        'numpy.testing',
        'numpy.f2py',
        'numpy.distutils',
        'numpy.doc',
        # Unused stdlib
        'unittest',
        'pdb',
        'doctest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MindScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disable UPX - avoids false antivirus positives
    icon='assets/mindscribe.icns' if platform.system() == "Darwin" else 'assets/mindscribe.ico',
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MindScribe',
)
