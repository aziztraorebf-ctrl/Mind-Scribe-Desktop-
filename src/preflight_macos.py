"""macOS preflight checks for MindScribe Desktop.

Run at app startup to verify that required system dependencies and
configuration are present before the app tries to use them.

Usage:
    from src.preflight_macos import run_preflight_checks

    warnings = run_preflight_checks()
    for w in warnings:
        print(w)
"""

import logging
import platform
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_env_search_dirs() -> list[Path]:
    """Return directories to search for .env file.

    Mirrors the logic in src.config.dotenv_loader._get_search_dirs().
    """
    dirs = []

    # Frozen mode (PyInstaller): directory containing the executable
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)

    # Current working directory
    dirs.append(Path.cwd())

    # Project root (3 levels up from this file) - only useful in dev mode
    project_root = Path(__file__).resolve().parent.parent
    if project_root not in dirs:
        dirs.append(project_root)

    return dirs


def _check_portaudio() -> list[str]:
    """Check that portaudio / sounddevice is available."""
    warnings = []
    try:
        import sounddevice  # noqa: F401
    except OSError as exc:
        warnings.append(
            f"sounddevice failed to load (portaudio missing?): {exc}\n"
            "  Fix: brew install portaudio"
        )
    except ImportError:
        warnings.append(
            "sounddevice is not installed.\n"
            "  Fix: pip install sounddevice"
        )
    return warnings


def _check_ffmpeg() -> list[str]:
    """Check that ffmpeg is on PATH."""
    warnings = []
    if shutil.which("ffmpeg") is None:
        warnings.append(
            "ffmpeg was not found on PATH.\n"
            "  Fix: brew install ffmpeg"
        )
    return warnings


def _check_pyqt6() -> list[str]:
    """Check that PyQt6 is importable."""
    warnings = []
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        warnings.append(
            "PyQt6 is not installed.\n"
            "  Fix: pip install PyQt6"
        )
    return warnings


def _check_pyobjc() -> list[str]:
    """Check that PyObjC (objc) is importable."""
    warnings = []
    try:
        import objc  # noqa: F401
    except ImportError:
        warnings.append(
            "PyObjC (objc) is not installed. pystray and pynput require it on macOS.\n"
            "  Fix: pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz"
        )
    return warnings


def _check_pillow() -> list[str]:
    """Check that Pillow is importable (needed for tray icons)."""
    warnings = []
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except ImportError:
        warnings.append(
            "Pillow is not installed (needed for tray icon generation).\n"
            "  Fix: pip install Pillow"
        )
    return warnings


def _check_pynput() -> list[str]:
    """Check that pynput is importable (needed for global hotkeys)."""
    warnings = []
    try:
        from pynput import keyboard  # noqa: F401
    except ImportError:
        warnings.append(
            "pynput is not installed (needed for global hotkeys).\n"
            "  Fix: pip install pynput"
        )
    return warnings


def _check_pystray() -> list[str]:
    """Check that pystray is importable (needed for system tray icon)."""
    warnings = []
    try:
        import pystray  # noqa: F401
    except ImportError:
        warnings.append(
            "pystray is not installed (needed for system tray icon).\n"
            "  Fix: pip install pystray"
        )
    return warnings


def _check_env_file() -> list[str]:
    """Check that a .env file exists in one of the expected locations."""
    warnings = []
    for d in _get_env_search_dirs():
        if (d / ".env").exists():
            return warnings

    search_dirs_str = ", ".join(str(d) for d in _get_env_search_dirs())
    warnings.append(
        f".env file not found in any of: {search_dirs_str}\n"
        "  Fix: Copy .env.example to .env and add your API keys."
    )
    return warnings


def run_preflight_checks() -> list[str]:
    """Run all macOS preflight checks.

    Returns a list of warning strings. An empty list means all checks passed.
    Silently returns an empty list if not running on macOS.
    """
    if platform.system() != "Darwin":
        return []

    logger.info("Running macOS preflight checks...")

    warnings: list[str] = []

    warnings.extend(_check_portaudio())
    warnings.extend(_check_ffmpeg())
    warnings.extend(_check_pyqt6())
    warnings.extend(_check_pyobjc())
    warnings.extend(_check_pillow())
    warnings.extend(_check_pynput())
    warnings.extend(_check_pystray())
    warnings.extend(_check_env_file())

    if warnings:
        logger.warning(
            "macOS preflight checks found %d issue(s):", len(warnings)
        )
        for w in warnings:
            logger.warning("  - %s", w.split("\n")[0])
    else:
        logger.info("All macOS preflight checks passed.")

    return warnings
