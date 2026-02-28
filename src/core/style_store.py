"""Transcription style profiles with JSON persistence."""

import json
import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

_BUILTIN_STYLES = [
    {
        "name": "Default",
        "description": "Standard faithful transcription, no special formatting",
        "prompt": "",
        "is_builtin": True,
    },
    {
        "name": "Message",
        "description": "Casual, conversational tone",
        "prompt": "Format as a casual message. Keep it conversational, don't over-correct punctuation.",
        "is_builtin": True,
    },
    {
        "name": "Email",
        "description": "Formal, complete sentences",
        "prompt": "Format as a professional email. Use complete sentences, proper punctuation, and formal tone.",
        "is_builtin": True,
    },
    {
        "name": "Code",
        "description": "Technical dictation, preserves names exactly",
        "prompt": "Technical dictation. Preserve function names, variable names, and technical terms exactly as spoken.",
        "is_builtin": True,
    },
    {
        "name": "Meeting Notes",
        "description": "Bullet points for action items",
        "prompt": "Format as meeting notes. Use bullet points for action items. Structure by topic.",
        "is_builtin": True,
    },
]


def _data_dir() -> Path:
    test_dir = os.environ.get("MINDSCRIBE_TEST_DIR")
    if test_dir:
        return Path(test_dir)
    home = Path.home()
    if platform.system() == "Darwin":
        base = home / "Library" / "Application Support" / "MindScribeDesktop"
    elif platform.system() == "Windows":
        base = home / "AppData" / "Local" / "MindScribeDesktop"
    else:
        base = home / ".config" / "mindscribe-desktop"
    return base


class StyleStore:
    """Manages built-in and custom transcription styles."""

    def __init__(self) -> None:
        data_dir = _data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        self._styles_path = data_dir / "styles.json"
        self._custom_styles: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._styles_path.exists():
            try:
                with open(self._styles_path, "r", encoding="utf-8") as f:
                    self._custom_styles = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load styles.json, starting fresh")
                self._custom_styles = []

    def _save(self) -> None:
        try:
            with open(self._styles_path, "w", encoding="utf-8") as f:
                json.dump(self._custom_styles, f, indent=2)
        except OSError:
            logger.error("Failed to save styles.json")

    def get_all_styles(self) -> list[dict]:
        """Return all styles (built-in + custom)."""
        custom_with_flag = [
            {**s, "is_builtin": False} for s in self._custom_styles
        ]
        return list(_BUILTIN_STYLES) + custom_with_flag

    def get_style(self, name: str) -> dict | None:
        """Get a specific style by name."""
        for style in self.get_all_styles():
            if style["name"] == name:
                return style
        return None

    def add_custom_style(self, name: str, description: str, prompt: str) -> None:
        """Add a custom style. Raises ValueError if name collides with built-in."""
        for builtin in _BUILTIN_STYLES:
            if builtin["name"] == name:
                raise ValueError(f"Cannot use built-in style name: {name}")
        # Remove existing custom style with same name
        self._custom_styles = [
            s for s in self._custom_styles if s["name"] != name
        ]
        self._custom_styles.append({
            "name": name,
            "description": description,
            "prompt": prompt,
        })
        self._save()

    def delete_custom_style(self, name: str) -> None:
        """Delete a custom style. Built-in styles cannot be deleted."""
        for builtin in _BUILTIN_STYLES:
            if builtin["name"] == name:
                raise ValueError(f"Cannot delete built-in style: {name}")
        self._custom_styles = [
            s for s in self._custom_styles if s["name"] != name
        ]
        self._save()

    def get_active_prompt(self, style_name: str) -> str:
        """Return the prompt text for the given style name."""
        style = self.get_style(style_name)
        if style is None:
            return ""
        return style["prompt"]
