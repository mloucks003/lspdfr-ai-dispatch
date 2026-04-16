# -*- mode: python ; coding: utf-8 -*-
# BlueLineDispatchPro — PyInstaller Build Spec
# Run: pyinstaller build.spec
# Output: dist/BlueLineDispatchPro/BlueLineDispatchPro.exe

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Collect vosk model data files (if bundled — optional, can ship separately)
# vosk_datas = collect_data_files('vosk')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config/settings.json',    'config'),
        ('config/audio_map.json',   'config'),
        ('audio',                   'audio'),
        # Uncomment to bundle model (adds ~40-500MB depending on model size):
        # ('models/vosk-model-en-us', 'models/vosk-model-en-us'),
    ],
    hiddenimports=[
        'vosk',
        'pyaudio',
        'pydub',
        'simpleaudio',
        'numpy',
        'scipy',
        'scipy.signal',
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'flask',
        'flask_cors',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'keyboard',
        'pystray',
        'pystray._win32',
        'requests',
        'tkinter',
        'tkinter.ttk',
        'win32api',
        'win32con',
        'win32gui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'IPython', 'jupyter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BlueLineDispatchPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,               # No console window — GUI only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                   # Add icon path here: 'assets/icon.ico'
    version_file=None,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BlueLineDispatchPro',
)
