"""Load environment variables from .env file."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _get_search_dirs() -> list[Path]:
    """Return directories to search for .env file, ordered by priority.

    When running as a PyInstaller frozen executable, prioritizes
    the directory containing the executable so users can place .env next to it.
    """
    dirs = []

    # Frozen mode (PyInstaller): directory containing the executable
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)

    # Current working directory
    dirs.append(Path.cwd())

    # Project root (3 levels up from this file) - only useful in dev mode
    project_root = Path(__file__).resolve().parent.parent.parent
    if project_root not in dirs:
        dirs.append(project_root)

    return dirs


def load_env() -> dict[str, str]:
    """Load .env from best available location and return API keys."""
    for d in _get_search_dirs():
        env_path = d / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            break

    return {
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    }
