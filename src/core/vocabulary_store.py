"""Persistent user vocabulary for Whisper prompt injection."""

import json
import platform
from pathlib import Path


def _vocab_path() -> Path:
    home = Path.home()
    if platform.system() == "Darwin":
        base = home / "Library" / "Application Support" / "MindScribeDesktop"
    elif platform.system() == "Windows":
        base = home / "AppData" / "Local" / "MindScribeDesktop"
    else:
        base = home / ".config" / "mindscribe-desktop"
    return base / "vocabulary.json"


class VocabularyStore:
    """Loads, saves, and injects custom words into the Whisper prompt."""

    def __init__(self) -> None:
        self._path = _vocab_path()
        self._words: list[str] = self._load()

    def _load(self) -> list[str]:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [str(w) for w in data if w]
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._words, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def words(self) -> list[str]:
        return list(self._words)

    def set_words(self, words: list[str]) -> None:
        """Replace the word list and persist."""
        self._words = [w.strip() for w in words if w.strip()]
        self.save()

    def build_prompt_suffix(self) -> str:
        """Return a string to append to the Whisper prompt, or empty string."""
        if not self._words:
            return ""
        return " " + ", ".join(self._words) + "."
