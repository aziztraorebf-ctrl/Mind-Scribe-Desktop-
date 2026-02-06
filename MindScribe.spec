# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for MindScribe Desktop (macOS / PyQt6).

Build command:
    pyinstaller MindScribe.spec --clean

Output:
    dist/MindScribe.app
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

sounddevice_data = collect_data_files('_sounddevice_data')
plyer_imports = collect_submodules('plyer.platforms.macosx')
pyqt6_imports = collect_submodules('PyQt6')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=sounddevice_data,
    hiddenimports=[
        # macOS platform backends
        'plyer.platforms.macosx',
        'plyer.platforms.macosx.notification',
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        # pystray no longer used (replaced by QSystemTrayIcon)
        # PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.sip',
        # App modules
        'src', 'src.app',
        'src.config', 'src.config.settings', 'src.config.dotenv_loader',
        'src.core', 'src.core.audio_recorder', 'src.core.chunker',
        'src.core.hotkey_manager', 'src.core.text_inserter', 'src.core.transcriber',
        'src.ui', 'src.ui.icons', 'src.ui.notification',
        'src.ui.overlay', 'src.ui.settings_window', 'src.ui.tray_icon',
        'src.preflight_macos',
        # audioop replacement
        'audioop_lts', 'audioop',
    ] + plyer_imports + pyqt6_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest', 'pytest_cov',
        'tkinter', '_tkinter', 'customtkinter',
        'numpy.testing', 'numpy.f2py', 'numpy.distutils', 'numpy.doc',
        'unittest', 'pdb', 'doctest',
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
    upx=False,
    icon='assets/mindscribe.icns',
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file='macos/entitlements.plist',
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

app = BUNDLE(
    coll,
    name='MindScribe.app',
    icon='assets/mindscribe.icns',
    bundle_identifier='com.mindscribe.desktop',
    info_plist={
        'CFBundleName': 'MindScribe',
        'CFBundleDisplayName': 'MindScribe Desktop',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSMinimumSystemVersion': '12.0',
        'NSHighResolutionCapable': True,
        'LSUIElement': True,
        'NSMicrophoneUsageDescription': 'MindScribe needs microphone access to record your voice for transcription.',
        'NSAppleEventsUsageDescription': 'MindScribe uses AppleScript to display native notifications.',
    },
)
