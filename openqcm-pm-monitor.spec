# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for openQCM-pm-monitor — Windows one-file build.

Build with:
    pyinstaller openqcm-pm-monitor.spec --clean --noconfirm

Output:
    dist/openQCM-pm-monitor.exe
"""

block_cipher = None


# ── Analysis: gather sources, data files, hidden imports ──
a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Bundled icons / logo — accessed at runtime via openqcm.paths.resource_path
        ('openqcm/icons/icon.ico',         'icons'),
        ('openqcm/icons/icon.png',         'icons'),
        ('openqcm/icons/openqcm-logo.png', 'icons'),
    ],
    hiddenimports=[
        # PyQtGraph has lazy submodule imports that PyInstaller sometimes misses
        'pyqtgraph',
        'pyqtgraph.Qt',
        # pyserial backend selected dynamically per platform
        'serial.tools.list_ports_windows',
        'serial.tools.list_ports_common',
        # SciPy submodules used by signal-processing path
        'scipy.signal',
        'scipy.interpolate',
        'scipy._lib.messagestream',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Tk/Tcl (we use Qt) — saves ~10 MB
        'tkinter', 'tcl', 'tk', '_tkinter',
        # Other GUI / scientific stacks not used
        'matplotlib', 'IPython', 'jupyter', 'notebook',
        'pytest', 'sphinx', 'pdb', 'doctest',
        # Heavy Qt modules we don't use — saves ~30 MB
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtNetwork', 'PyQt5.QtSql',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtBluetooth', 'PyQt5.QtPositioning', 'PyQt5.QtNfc',
        'PyQt5.QtSensors', 'PyQt5.QtSerialPort', 'PyQt5.QtSvg',
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtTest', 'PyQt5.QtHelp', 'PyQt5.QtDesigner',
        'PyQt5.QtXml', 'PyQt5.QtXmlPatterns',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


# ── Splash screen: shown immediately at launch, masks one-file extraction ──
splash = Splash(
    'openqcm/icons/openqcm-logo.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
    always_on_top=True,
)


# ── EXE: single file, no console, custom icon, version metadata ──
exe = EXE(
    pyz,
    splash,
    splash.binaries,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='openQCM-pm-monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX slows startup more than it shrinks the file
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # Windows GUI app, hide console
    disable_windowed_traceback=False,
    icon='openqcm/icons/icon.ico',
    version='version_info.txt',
)
