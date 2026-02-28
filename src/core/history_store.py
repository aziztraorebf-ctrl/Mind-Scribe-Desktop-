"""SQLite persistence for transcription history."""

import logging
import os
import platform
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


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


class HistoryStore:
    """SQLite-backed transcription history."""

    def __init__(self) -> None:
        db_dir = _data_dir()
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / "history.db"
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                duration_seconds REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def add(self, text: str, duration_seconds: float = 0.0) -> int:
        """Insert a transcription entry and return its row id."""
        word_count = len(text.split())
        created_at = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO transcriptions (text, word_count, duration_seconds, created_at) "
            "VALUES (?, ?, ?, ?)",
            (text, word_count, duration_seconds, created_at),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Return most recent entries ordered by created_at DESC."""
        cursor = self._conn.execute(
            "SELECT id, text, word_count, duration_seconds, created_at "
            "FROM transcriptions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete(self, entry_id: int) -> None:
        """Delete a transcription entry by id."""
        self._conn.execute(
            "DELETE FROM transcriptions WHERE id = ?", (entry_id,)
        )
        self._conn.commit()

    def get_stats(self) -> dict:
        """Return streak_days, total_words, and avg_wpm."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(word_count), 0) AS total_words, "
            "COALESCE(SUM(duration_seconds), 0.0) AS total_duration "
            "FROM transcriptions"
        ).fetchone()

        total_words = row["total_words"]
        total_duration = row["total_duration"]

        total_minutes = total_duration / 60.0
        avg_wpm = round(total_words / total_minutes, 1) if total_minutes > 0 else 0.0

        streak_days = self._calc_streak()

        return {
            "streak_days": streak_days,
            "total_words": total_words,
            "avg_wpm": avg_wpm,
        }

    def _calc_streak(self) -> int:
        """Count consecutive days backward from today with at least 1 entry."""
        cursor = self._conn.execute(
            "SELECT DISTINCT date(created_at) AS day FROM transcriptions "
            "ORDER BY day DESC"
        )
        days = {row["day"] for row in cursor.fetchall()}
        if not days:
            return 0

        streak = 0
        check = datetime.now().date()
        while check.isoformat() in days:
            streak += 1
            check -= timedelta(days=1)
        return streak
