"""
Path helpers — work both during development and inside a PyInstaller bundle.

PyInstaller in --onefile mode extracts read-only assets (icons, etc.) to a
temporary directory exposed as ``sys._MEIPASS`` that is wiped when the app
exits. Anything we need to *write* (CSV logs, persisted config) must live
next to the executable instead.

Usage:
    from openqcm.paths import resource_path, app_data_dir
    icon_path = resource_path('icons/icon.png')
    logs_dir  = app_data_dir()           # creates the dir if missing
"""

import os
import sys


def is_frozen() -> bool:
    """True when running inside a PyInstaller-built executable."""
    return getattr(sys, 'frozen', False)


def resource_path(relative: str) -> str:
    """Absolute path to a bundled read-only resource.

    In dev: relative to the ``openqcm/`` package root.
    In frozen one-file: relative to ``sys._MEIPASS``.
    """
    if is_frozen():
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def app_data_dir() -> str:
    """Directory for writable runtime data (CSV logs, persisted state).

    In dev: ``<project_root>/data``.
    In frozen: ``<exe_dir>/data``.

    The directory is created if it does not exist.
    """
    if is_frozen():
        base = os.path.dirname(sys.executable)
    else:
        # openqcm/<this file> → project root is two levels up
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(base, 'data')
    os.makedirs(target, exist_ok=True)
    return target
