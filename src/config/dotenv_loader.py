"""Load environment variables from .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> dict[str, str]:
    """Load .env from project root and return API keys."""
    # Search for .env in current dir and parent dirs
    search_dirs = [
        Path.cwd(),
        Path(__file__).resolve().parent.parent.parent,  # project root
    ]

    for d in search_dirs:
        env_path = d / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            break

    return {
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    }
