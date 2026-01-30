"""Application settings model with JSON persistence."""

import json
import platform
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def _default_hotkey() -> str:
    if platform.system() == "Darwin":
        return "<cmd>+<shift>+<space>"
    return "<ctrl>+<shift>+<space>"


def _config_dir() -> Path:
    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData" / "Local" / "MindScribeDesktop"
    elif platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "MindScribeDesktop"
    return home / ".config" / "mindscribe-desktop"


@dataclass
class Settings:
    # API
    groq_api_key: str = ""
    openai_api_key: str = ""
    primary_provider: str = "groq"  # "groq" or "openai"
    whisper_model: str = "whisper-large-v3"  # whisper-large-v3 or whisper-large-v3-turbo

    # Recording
    hotkey: str = field(default_factory=_default_hotkey)
    record_mode: str = "toggle"  # "toggle" or "hold"
    sample_rate: int = 16000  # 16kHz optimal for Whisper
    channels: int = 1  # Mono
    input_device: Optional[int] = None  # None = system default

    # Transcription
    language: str = "fr"  # ISO-639-1 code
    prompt: str = "Transcription d'un developpeur logiciel francophone."
    post_process: bool = False  # Clean up transcription via LLM

    # App
    auto_start: bool = False
    show_notifications: bool = True
    restore_clipboard: bool = True
    clipboard_restore_delay: float = 0.5  # seconds

    @classmethod
    def config_path(cls) -> Path:
        return _config_dir() / "config.json"

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from JSON file, falling back to defaults."""
        path = cls.config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                known_fields = {f.name for f in cls.__dataclass_fields__.values()}
                filtered = {k: v for k, v in data.items() if k in known_fields}
                return cls(**filtered)
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        """Persist settings to JSON file."""
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # Never persist API keys to config file - they come from .env
        data.pop("groq_api_key", None)
        data.pop("openai_api_key", None)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def merge_env(self, groq_key: str = "", openai_key: str = "") -> None:
        """Merge API keys from environment variables."""
        if groq_key:
            self.groq_api_key = groq_key
        if openai_key:
            self.openai_api_key = openai_key
