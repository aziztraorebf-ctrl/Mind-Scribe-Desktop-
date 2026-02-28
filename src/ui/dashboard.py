"""Dashboard window with sidebar navigation for MindScribe Desktop.

Provides Home (history/stats), Dictionary (vocabulary editor), Styles
(transcription style selection), and Settings tabs in a single PyQt6 window.
"""

import logging
import platform
import re
import threading
from datetime import datetime
from typing import Callable

import pyperclip
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings
from src.core.audio_recorder import AudioRecorder

logger = logging.getLogger(__name__)

# Theme palettes
_DARK_THEME = {
    "BG": "#1e1e2e",
    "BG_SIDEBAR": "#16162a",
    "BG_FIELD": "#2a2a3e",
    "FG": "#e0e0e0",
    "FG_DIM": "#999999",
    "ACCENT": "#3b82f6",
    "ACCENT_HOVER": "#2563eb",
    "DANGER": "#ef4444",
    "TOGGLE_LABEL": "Light Mode",
    "SECTION_COLOR": "white",
}
_LIGHT_THEME = {
    "BG": "#f5f5f7",
    "BG_SIDEBAR": "#e8e8ed",
    "BG_FIELD": "#ffffff",
    "FG": "#1d1d1f",
    "FG_DIM": "#6e6e73",
    "ACCENT": "#2563eb",
    "ACCENT_HOVER": "#1d4ed8",
    "DANGER": "#dc2626",
    "TOGGLE_LABEL": "Dark Mode",
    "SECTION_COLOR": "#1d1d1f",
}

# Module-level active theme (defaults to dark)
_theme = dict(_DARK_THEME)


def _c(key: str) -> str:
    """Read a color from the currently active theme."""
    return _theme[key]


# Module-level color aliases — these are NOT constants; they are re-read each time
# a build method runs because they call _c() which reads _theme at call time.
# We define them as module-level callables that build methods call inline.
def _BG() -> str: return _theme["BG"]
def _BG_SIDEBAR() -> str: return _theme["BG_SIDEBAR"]
def _BG_FIELD() -> str: return _theme["BG_FIELD"]
def _FG() -> str: return _theme["FG"]
def _FG_DIM() -> str: return _theme["FG_DIM"]
def _ACCENT() -> str: return _theme["ACCENT"]
def _ACCENT_HOVER() -> str: return _theme["ACCENT_HOVER"]
def _DANGER() -> str: return _theme["DANGER"]
def _BORDER() -> str: return "#3a3a50" if _theme["BG"] == _DARK_THEME["BG"] else "#c7c7cc"

SIDEBAR_WIDTH = 160
WINDOW_W = 740
WINDOW_H = 560

_IS_MAC = platform.system() == "Darwin"
_UI_FONT = ".AppleSystemUIFont" if _IS_MAC else "Segoe UI"
_MONO_FONT = "Menlo" if _IS_MAC else "Consolas"

_NAV_ITEMS = ["Home", "Dictionary", "Styles", "Settings"]


def _build_global_stylesheet(t: dict) -> str:
    """Return a window-level QSS that themes all child widgets."""
    return f"""
QWidget#dashboard_root {{
    background: {t['BG']};
}}
QWidget#dashboard_sidebar {{
    background: {t['BG_SIDEBAR']};
}}
QStackedWidget, QWidget#dashboard_content {{
    background: {t['BG']};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {t['BG']};
    border: none;
}}
QLabel {{
    color: {t['FG']};
    background: transparent;
}}
QTextEdit {{
    background: {t['BG_FIELD']};
    color: {t['FG']};
    border: 1px solid {'#3a3a50' if t['BG'] == _DARK_THEME['BG'] else '#c7c7cc'};
    border-radius: 6px;
    padding: 8px;
}}
QComboBox {{
    background: {t['BG_FIELD']};
    color: {t['FG']};
    border: 1px solid {'#3a3a50' if t['BG'] == _DARK_THEME['BG'] else '#c7c7cc'};
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 22px;
}}
QComboBox QAbstractItemView {{
    background: {t['BG_FIELD']};
    color: {t['FG']};
    selection-background-color: {t['ACCENT']};
    selection-color: white;
}}
QCheckBox {{
    color: {t['FG']};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {'#666' if t['BG'] == _DARK_THEME['BG'] else '#aaa'};
    background: {t['BG_FIELD']};
}}
QCheckBox::indicator:checked {{
    background: {t['ACCENT']};
    border-color: {t['ACCENT']};
}}
QFrame[class="history_entry"], QFrame[class="style_card"] {{
    background: {t['BG_FIELD']};
    border-radius: 8px;
}}
"""


def _nav_btn_style(t: dict) -> str:
    return f"""
QPushButton {{
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    color: {t['FG_DIM']};
    background: transparent;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {t['BG_FIELD']};
    color: {t['FG']};
}}
"""


def _nav_btn_active_style(t: dict) -> str:
    return f"""
QPushButton {{
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    color: {t['ACCENT']};
    background: {t['BG_FIELD']};
    font-size: 13px;
    font-weight: 600;
}}
"""

# Language options
LANGUAGE_OPTIONS = {
    "Francais": "fr",
    "English": "en",
    "Auto-detect": "auto",
}
LANGUAGE_LABELS = list(LANGUAGE_OPTIONS.keys())

PROVIDER_LABELS = {"groq": "Groq (Recommended)", "openai": "OpenAI"}
MODEL_LABELS = {
    "whisper-large-v3": "whisper-large-v3 (Best accuracy)",
    "whisper-large-v3-turbo": "whisper-large-v3-turbo (Faster)",
}
RECORD_MODE_LABELS = {
    "toggle": "Toggle (press to start/stop)",
    "hold": "Hold (hold to record)",
}

_MOD = "<cmd>" if _IS_MAC else "<ctrl>"
_MOD_LABEL = "Cmd" if _IS_MAC else "Ctrl"
HOTKEY_PRESETS = {
    f"{_MOD}+<shift>+<space>": f"{_MOD_LABEL} + Shift + Space (default)",
    f"{_MOD}+<shift>+r": f"{_MOD_LABEL} + Shift + R",
    f"{_MOD}+<shift>+d": f"{_MOD_LABEL} + Shift + D",
    "<f9>": "F9",
    "<f8>": "F8",
    "<f7>": "F7",
    f"{_MOD}+<alt>+<space>": f"{_MOD_LABEL} + Alt + Space",
    f"{_MOD}+<alt>": f"{_MOD_LABEL} + Alt",
}
HOTKEY_PRESET_LABELS = list(HOTKEY_PRESETS.values())


class _HistoryEntry(QFrame):
    """A single transcription history entry widget."""

    def __init__(self, entry: dict, on_delete: Callable, parent=None) -> None:
        super().__init__(parent)
        self._entry = entry
        self._on_delete = on_delete
        self._expanded = False

        self.setStyleSheet(
            f"QFrame {{ background: {_BG_FIELD()}; border-radius: 8px; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: timestamp + word count + action buttons
        header = QHBoxLayout()
        try:
            dt = datetime.fromisoformat(entry["created_at"])
            ts_str = dt.strftime("%b %d at %-I:%M %p")
        except (ValueError, KeyError):
            ts_str = entry.get("created_at", "")
        ts_label = QLabel(ts_str)
        ts_label.setStyleSheet(f"color: {_FG_DIM()}; font-size: 11px; background: transparent;")
        header.addWidget(ts_label)

        wc = entry.get("word_count", 0)
        wc_label = QLabel(f"{wc}w")
        wc_label.setStyleSheet(f"color: {_FG_DIM()}; font-size: 11px; background: transparent;")
        header.addWidget(wc_label)
        header.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(24)
        copy_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT()}; color: white; border: none; "
            f"border-radius: 4px; padding: 2px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOVER()}; }}"
        )
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._copy)
        header.addWidget(copy_btn)

        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(24)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: {_DANGER()}; color: white; border: none; "
            f"border-radius: 4px; padding: 2px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #dc2626; }}"
        )
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self._on_delete(self._entry["id"], self))
        header.addWidget(del_btn)

        layout.addLayout(header)

        # Preview text (click to expand full text)
        text = entry.get("text", "")
        preview = text[:120] + ("..." if len(text) > 120 else "")
        self._preview_label = QLabel(preview)
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(f"color: {_FG()}; font-size: 13px; background: transparent;")
        layout.addWidget(self._preview_label)

        self._full_label = QLabel(text)
        self._full_label.setWordWrap(True)
        self._full_label.setStyleSheet(f"color: {_FG()}; font-size: 13px; background: transparent;")
        self._full_label.setVisible(False)
        layout.addWidget(self._full_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._expanded = not self._expanded
        self._preview_label.setVisible(not self._expanded)
        self._full_label.setVisible(self._expanded)
        super().mousePressEvent(event)

    def _copy(self) -> None:
        pyperclip.copy(self._entry.get("text", ""))


class _StyleCard(QFrame):
    """A style selection card."""

    def __init__(self, style: dict, is_active: bool, on_click: Callable, parent=None) -> None:
        super().__init__(parent)
        self._style = style
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_active(is_active)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        name_label = QLabel(style["name"])
        name_label.setStyleSheet(f"color: {_FG()}; font-size: 13px; font-weight: 600; background: transparent;")
        layout.addWidget(name_label)

        desc_label = QLabel(style.get("description", ""))
        desc_label.setStyleSheet(f"color: {_FG_DIM()}; font-size: 11px; background: transparent;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

    def _set_active(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                f"QFrame {{ background: {_BG_FIELD()}; border-left: 3px solid {_ACCENT()}; border-radius: 6px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {_BG_FIELD()}; border: none; border-radius: 6px; }}"
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._on_click(self._style)
        super().mousePressEvent(event)


class Dashboard(QWidget):
    """Main dashboard window with sidebar navigation and stacked content pages."""

    _sig_open = pyqtSignal()
    _sig_raise = pyqtSignal()
    _sig_refresh_home = pyqtSignal()

    def __init__(
        self,
        history_store=None,
        style_store=None,
        vocabulary=None,
        settings: Settings | None = None,
        on_style_change: Callable[[str, str], None] | None = None,
        on_settings_save: Callable[[Settings], None] | None = None,
    ) -> None:
        super().__init__()
        self._history_store = history_store
        self._style_store = style_store
        self._vocabulary = vocabulary
        self._settings = settings
        self._on_style_change = on_style_change
        self._on_settings_save = on_settings_save
        self._hotkey_manager = None
        self._is_open = False
        self._built = False
        self._is_dark = True
        self._nav_buttons: list[QPushButton] = []
        self._theme_btn: QPushButton | None = None
        self._active_style_name = settings.active_style if settings else "Default"

        # Settings widget references
        self._lang_combo: QComboBox | None = None
        self._provider_combo: QComboBox | None = None
        self._model_combo: QComboBox | None = None
        self._model_hint: QLabel | None = None
        self._prompt_text: QTextEdit | None = None
        self._post_process_cb: QCheckBox | None = None
        self._device_combo: QComboBox | None = None
        self._devices: list[dict] = []
        self._mode_combo: QComboBox | None = None
        self._hotkey_combo: QComboBox | None = None
        self._notif_cb: QCheckBox | None = None
        self._clipboard_cb: QCheckBox | None = None
        self._testing_hotkey = False
        self._test_combo_label = ""
        self._test_target_keys: set[int] = set()
        self._test_pressed_keys: set[int] = set()
        self._test_btn: QPushButton | None = None
        self._hotkey_test_label: QLabel | None = None
        self._settings_status_label: QLabel | None = None

        self._sig_open.connect(self._open_or_refresh)
        self._sig_raise.connect(self._raise_window)
        self._sig_refresh_home.connect(self._refresh_home_tab)

    def set_hotkey_manager(self, manager) -> None:
        self._hotkey_manager = manager

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        """Open the dashboard (thread-safe)."""
        if self._is_open:
            self._sig_raise.emit()
            return
        self._sig_open.emit()

    def _raise_window(self) -> None:
        self._sig_refresh_home.emit()
        self.raise_()
        self.activateWindow()

    def _open_or_refresh(self) -> None:
        if not self._built:
            self._build_window()
        else:
            self._refresh_home_tab()
            self._is_open = True
            self.show()
            self.raise_()
            self.activateWindow()

    def _build_window(self) -> None:
        """Build the dashboard UI (lazy, called once or after theme change)."""
        self.setObjectName("dashboard_root")
        self.setWindowTitle("MindScribe Desktop - Dashboard")
        self.setFixedSize(WINDOW_W, WINDOW_H)
        self.setWindowFlag(Qt.WindowType.Window)
        self.setStyleSheet(f"QWidget#dashboard_root {{ background: {_BG()}; }}")

        # Root layout holds a single replaceable container widget.
        # This is the key to safe theme rebuilding: _rebuild_window() only
        # replaces _container, never touching the root layout itself.
        if self.layout() is None:
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

        self._container = QWidget()
        main_layout = QHBoxLayout(self._container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"background: {_BG_SIDEBAR()}; border: none;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)
        sidebar_layout.setSpacing(4)

        for i, label in enumerate(_NAV_ITEMS):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            self._nav_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Theme toggle button at bottom of sidebar
        self._theme_btn = QPushButton(_theme["TOGGLE_LABEL"])
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_FIELD()}; color: {_FG_DIM()}; border: none; "
            f"border-radius: 6px; padding: 8px 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {_FG()}; }}"
        )
        self._theme_btn.clicked.connect(self._toggle_theme)
        sidebar_layout.addWidget(self._theme_btn)

        main_layout.addWidget(sidebar)

        # Stacked content area
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {_BG()};")

        self._home_page = self._build_home_tab()
        self._stack.addWidget(self._home_page)
        self._stack.addWidget(self._build_dictionary_tab())
        self._stack.addWidget(self._build_styles_tab())
        self._stack.addWidget(self._build_settings_tab())

        main_layout.addWidget(self._stack)

        self.layout().addWidget(self._container)
        self._switch_tab(0)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - WINDOW_W) // 2
            y = (geo.height() - WINDOW_H) // 2
            self.move(x, y)

        self._built = True
        self._is_open = True
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- Theme toggle ----

    def _toggle_theme(self) -> None:
        """Switch between dark and light themes by rebuilding the window."""
        global _theme
        self._is_dark = not self._is_dark
        _theme = dict(_DARK_THEME if self._is_dark else _LIGHT_THEME)
        # Defer rebuild so Qt finishes processing the button click before
        # we destroy the widget tree (destroying mid-event causes abort).
        QTimer.singleShot(0, self._rebuild_window)

    def _rebuild_window(self) -> None:
        """Replace the container widget with a freshly built one (theme change)."""
        self._nav_buttons = []
        # Detach and schedule deletion of the old container.
        # The root QVBoxLayout(self) stays intact — only _container is swapped.
        if hasattr(self, "_container") and self._container is not None:
            self._container.setParent(None)
            self._container.deleteLater()
            self._container = None
        self._built = False
        self._build_window()

    # ---- Home Tab ----

    def _build_home_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_BG()};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Stats row with 3 cards
        stats = {"streak_days": 0, "total_words": 0, "avg_wpm": 0.0}
        if self._history_store:
            try:
                stats = self._history_store.get_stats()
            except Exception:
                logger.warning("Failed to load stats")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._stat_labels: dict[str, tuple] = {}

        for key, label_text, fmt in [
            ("streak_days", "Streak", lambda v: f"{v} days"),
            ("total_words", "Total Words", str),
            ("avg_wpm", "Avg WPM", lambda v: f"{float(v):.1f}"),
        ]:
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background: {_BG_FIELD()}; border-radius: 8px; }}")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            val_lbl = QLabel(fmt(stats[key]))
            val_lbl.setStyleSheet(f"color: {_ACCENT()}; font-size: 18px; font-weight: 700; background: transparent;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(val_lbl)
            name_lbl = QLabel(label_text)
            name_lbl.setStyleSheet(f"color: {_FG_DIM()}; font-size: 11px; background: transparent;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(name_lbl)
            stats_row.addWidget(card)
            self._stat_labels[key] = (val_lbl, fmt)

        layout.addLayout(stats_row)

        # Scrollable history list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_BG()}; border: none; }}")

        self._history_container = QWidget()
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(8)

        self._populate_history()

        scroll.setWidget(self._history_container)
        layout.addWidget(scroll)

        return page

    def _populate_history(self) -> None:
        """Clear and repopulate history list from DB."""
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        entries = []
        if self._history_store:
            try:
                entries = self._history_store.get_recent()
            except Exception:
                logger.warning("Failed to load history entries")

        if entries:
            for entry in entries:
                widget = _HistoryEntry(entry, on_delete=self._delete_entry)
                self._history_layout.addWidget(widget)
        else:
            empty_label = QLabel("No transcriptions yet. Start dictating!")
            empty_label.setStyleSheet(f"color: {_FG_DIM()}; font-size: 14px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_layout.addWidget(empty_label)

        self._history_layout.addStretch()

    def _refresh_home_tab(self) -> None:
        """Reload stats and history from DB (called on every open)."""
        if not self._built:
            return

        stats = {"streak_days": 0, "total_words": 0, "avg_wpm": 0.0}
        if self._history_store:
            try:
                stats = self._history_store.get_stats()
            except Exception:
                pass

        for key, (val_lbl, fmt) in self._stat_labels.items():
            val_lbl.setText(fmt(stats[key]))

        self._populate_history()

    def _delete_entry(self, entry_id: int, widget: QWidget) -> None:
        if self._history_store:
            try:
                self._history_store.delete(entry_id)
            except Exception:
                logger.error("Failed to delete entry %d", entry_id)
                return
        widget.setParent(None)
        widget.deleteLater()

    # ---- Dictionary Tab ----

    def _build_dictionary_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_BG()};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel("Personal Dictionary")
        title.setStyleSheet(f"color: {_FG()}; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel("One word or phrase per line. Always recognized correctly by Whisper.")
        subtitle.setStyleSheet(f"color: {_FG_DIM()}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._vocab_text = QTextEdit()
        self._vocab_text.setStyleSheet(
            f"QTextEdit {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 6px; padding: 8px; font-size: 13px; }}"
        )
        if self._vocabulary:
            try:
                self._vocab_text.setPlainText("\n".join(self._vocabulary.words))
            except Exception:
                pass
        layout.addWidget(self._vocab_text)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT()}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOVER()}; }}"
        )
        save_btn.clicked.connect(self._save_vocabulary)
        layout.addWidget(save_btn)

        return page

    def _save_vocabulary(self) -> None:
        if not self._vocabulary:
            return
        words = [w.strip() for w in self._vocab_text.toPlainText().split("\n") if w.strip()]
        try:
            self._vocabulary.set_words(words)
            logger.info("Vocabulary saved: %d words", len(words))
        except Exception:
            logger.error("Failed to save vocabulary")

    # ---- Styles Tab ----

    def _build_styles_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_BG()};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel("Transcription Styles")
        title.setStyleSheet(f"color: {_FG()}; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel("Select a style to change how your dictation is formatted.")
        subtitle.setStyleSheet(f"color: {_FG_DIM()}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_BG()}; border: none; }}")

        self._styles_container = QWidget()
        self._styles_layout = QVBoxLayout(self._styles_container)
        self._styles_layout.setContentsMargins(0, 0, 0, 0)
        self._styles_layout.setSpacing(8)

        self._rebuild_style_cards()

        self._styles_layout.addStretch()
        scroll.setWidget(self._styles_container)
        layout.addWidget(scroll)

        add_btn = QPushButton("+ Add Custom Style")
        add_btn.setFixedHeight(36)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 6px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #3a3a50; }}"
        )
        add_btn.clicked.connect(self._add_custom_style_dialog)
        layout.addWidget(add_btn)

        return page

    def _rebuild_style_cards(self) -> None:
        while self._styles_layout.count():
            item = self._styles_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        styles = []
        if self._style_store:
            try:
                styles = self._style_store.get_all_styles()
            except Exception:
                logger.warning("Failed to load styles")

        for style in styles:
            is_active = style["name"] == self._active_style_name
            card = _StyleCard(style, is_active, on_click=self._select_style)
            self._styles_layout.addWidget(card)

            if not style.get("is_builtin", True):
                del_btn = QPushButton(f"Delete '{style['name']}'")
                del_btn.setFixedHeight(24)
                del_btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {_DANGER()}; border: none; "
                    f"font-size: 11px; }} QPushButton:hover {{ color: #dc2626; }}"
                )
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                name = style["name"]
                del_btn.clicked.connect(lambda checked, n=name: self._delete_custom_style(n))
                self._styles_layout.addWidget(del_btn)

        self._styles_layout.addStretch()

    def _select_style(self, style: dict) -> None:
        self._active_style_name = style["name"]
        if self._on_style_change:
            self._on_style_change(style["name"], style.get("prompt", ""))
        self._rebuild_style_cards()

    def _add_custom_style_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Custom Style")
        dialog.setFixedSize(400, 300)
        dialog.setStyleSheet(f"QDialog {{ background: {_BG()}; }}")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        name_label = QLabel("Style Name")
        name_label.setStyleSheet(f"color: {_FG()}; font-size: 12px;")
        layout.addWidget(name_label)

        name_input = QLineEdit()
        name_input.setStyleSheet(
            f"QLineEdit {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 6px; }}"
        )
        layout.addWidget(name_input)

        prompt_label = QLabel("Prompt")
        prompt_label.setStyleSheet(f"color: {_FG()}; font-size: 12px;")
        layout.addWidget(prompt_label)

        prompt_input = QTextEdit()
        prompt_input.setStyleSheet(
            f"QTextEdit {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 6px; }}"
        )
        layout.addWidget(prompt_input)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_FIELD()}; color: {_FG()}; border: none; border-radius: 4px; padding: 6px 16px; }}"
        )
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT()}; color: white; border: none; border-radius: 4px; padding: 6px 16px; }}"
        )
        save_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            prompt = prompt_input.toPlainText().strip()
            if name and self._style_store:
                try:
                    self._style_store.add_custom_style(name, "", prompt)
                    self._rebuild_style_cards()
                except ValueError as e:
                    logger.warning("Cannot add style: %s", e)

    def _delete_custom_style(self, name: str) -> None:
        if self._style_store:
            try:
                self._style_store.delete_custom_style(name)
                self._rebuild_style_cards()
            except ValueError as e:
                logger.warning("Cannot delete style: %s", e)

    # ---- Settings Tab ----

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {_BG()};")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_BG()}; border: none; }}")

        inner = QWidget()
        inner.setStyleSheet(f"background: {_BG()};")
        form = QVBoxLayout(inner)
        form.setContentsMargins(20, 20, 20, 12)
        form.setSpacing(4)

        # Transcription section
        self._settings_add_section(form, "Transcription")

        self._settings_add_label(form, "Language")
        current_lang = _code_to_label(
            self._settings.language if self._settings else "fr", LANGUAGE_OPTIONS
        )
        self._lang_combo = self._settings_add_combo(form, LANGUAGE_LABELS, current_lang)

        self._settings_add_label(form, "Primary Provider")
        provider_labels = list(PROVIDER_LABELS.values())
        current_provider = PROVIDER_LABELS.get(
            self._settings.primary_provider if self._settings else "groq", provider_labels[0]
        )
        self._provider_combo = self._settings_add_combo(form, provider_labels, current_provider)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)

        self._settings_add_label(form, "Whisper Model")
        model_labels = list(MODEL_LABELS.values())
        current_model = MODEL_LABELS.get(
            self._settings.whisper_model if self._settings else "whisper-large-v3", model_labels[0]
        )
        self._model_combo = self._settings_add_combo(form, model_labels, current_model)

        self._model_hint = QLabel("")
        self._model_hint.setStyleSheet(f"color: {_FG_DIM()}; font-size: 10px;")
        self._model_hint.setFont(QFont(_MONO_FONT, 10))
        form.addWidget(self._model_hint)
        self._on_provider_changed()

        self._settings_add_label(form, "Context Prompt (helps Whisper accuracy)")
        self._prompt_text = QTextEdit()
        self._prompt_text.setFont(QFont(_UI_FONT, 10))
        self._prompt_text.setFixedHeight(70)
        self._prompt_text.setStyleSheet(
            f"QTextEdit {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 4px; }}"
        )
        if self._settings:
            self._prompt_text.setPlainText(self._settings.prompt)
        form.addWidget(self._prompt_text)
        self._settings_add_spacer(form)

        self._post_process_cb = QCheckBox("Clean up text with LLM (fix punctuation, remove fillers)")
        self._post_process_cb.setStyleSheet(f"color: {_FG()};")
        self._post_process_cb.setFont(QFont(_UI_FONT, 10))
        if self._settings:
            self._post_process_cb.setChecked(self._settings.post_process)
        form.addWidget(self._post_process_cb)
        self._settings_add_spacer(form)

        # Recording section
        self._settings_add_section(form, "Recording")

        self._settings_add_label(form, "Microphone")
        self._device_combo = self._settings_add_combo(form, ["Loading..."], "Loading...")
        threading.Thread(target=self._load_devices, daemon=True).start()

        self._settings_add_label(form, "Record Mode")
        mode_labels = list(RECORD_MODE_LABELS.values())
        current_mode = RECORD_MODE_LABELS.get(
            self._settings.record_mode if self._settings else "toggle", mode_labels[0]
        )
        self._mode_combo = self._settings_add_combo(form, mode_labels, current_mode)

        self._settings_add_label(form, "Hotkey")
        hotkey_row = QHBoxLayout()
        current_hotkey_label = _combo_to_preset_label(
            self._settings.hotkey if self._settings else f"{_MOD}+<shift>+<space>"
        )
        self._hotkey_combo = QComboBox()
        self._hotkey_combo.setStyleSheet(
            f"QComboBox {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 5px 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {_BG_FIELD()}; color: {_FG()}; "
            f"selection-background-color: {_ACCENT()}; }}"
        )
        self._hotkey_combo.addItems(HOTKEY_PRESET_LABELS)
        self._hotkey_combo.setCurrentText(current_hotkey_label)
        self._hotkey_combo.setMinimumWidth(250)
        hotkey_row.addWidget(self._hotkey_combo)

        self._test_btn = QPushButton("Test")
        self._test_btn.setFont(QFont(_UI_FONT, 9))
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT()}; color: white; border: none; "
            f"padding: 5px 12px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOVER()}; }}"
        )
        self._test_btn.clicked.connect(self._test_hotkey)
        hotkey_row.addWidget(self._test_btn)
        hotkey_row.addStretch()
        form.addLayout(hotkey_row)

        self._hotkey_test_label = QLabel("")
        self._hotkey_test_label.setStyleSheet(f"color: {_FG_DIM()}; font-size: 10px;")
        self._hotkey_test_label.setFont(QFont(_MONO_FONT, 10))
        form.addWidget(self._hotkey_test_label)
        self._settings_add_spacer(form)

        # Application section
        self._settings_add_section(form, "Application")

        self._notif_cb = QCheckBox("Show notifications")
        self._notif_cb.setStyleSheet(f"color: {_FG()};")
        self._notif_cb.setFont(QFont(_UI_FONT, 10))
        if self._settings:
            self._notif_cb.setChecked(self._settings.show_notifications)
        form.addWidget(self._notif_cb)

        self._clipboard_cb = QCheckBox("Restore clipboard after paste")
        self._clipboard_cb.setStyleSheet(f"color: {_FG()};")
        self._clipboard_cb.setFont(QFont(_UI_FONT, 10))
        if self._settings:
            self._clipboard_cb.setChecked(self._settings.restore_clipboard)
        form.addWidget(self._clipboard_cb)

        form.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # Save button bar (fixed at bottom)
        btn_bar = QWidget()
        btn_bar.setStyleSheet(f"background: {_BG()};")
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(20, 8, 20, 16)

        self._settings_status_label = QLabel("")
        self._settings_status_label.setStyleSheet("color: #22c55e; font-size: 12px;")
        btn_bar_layout.addWidget(self._settings_status_label)
        btn_bar_layout.addStretch()

        save_btn = QPushButton("Save Settings")
        save_btn.setFixedHeight(36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT()}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; padding: 0 20px; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOVER()}; }}"
        )
        save_btn.clicked.connect(self._save_settings)
        btn_bar_layout.addWidget(save_btn)
        outer.addWidget(btn_bar)

        return page

    # Settings tab helpers

    def _settings_add_section(self, layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(f"color: {_FG()}; font-size: 13px; font-weight: 700;")
        label.setFont(QFont(_UI_FONT, 12, QFont.Weight.Bold))
        layout.addWidget(label)

    def _settings_add_label(self, layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(f"color: {_FG()}; font-size: 11px;")
        label.setFont(QFont(_UI_FONT, 10))
        label.setContentsMargins(4, 0, 0, 0)
        layout.addWidget(label)

    def _settings_add_combo(self, layout: QVBoxLayout, items: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        combo.setStyleSheet(
            f"QComboBox {{ background: {_BG_FIELD()}; color: {_FG()}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 5px 8px; min-height: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {_BG_FIELD()}; color: {_FG()}; "
            f"selection-background-color: {_ACCENT()}; }}"
        )
        combo.addItems(items)
        combo.setCurrentText(current)
        combo.setMinimumWidth(300)
        layout.addWidget(combo)
        return combo

    def _settings_add_spacer(self, layout: QVBoxLayout) -> None:
        spacer = QWidget()
        spacer.setFixedHeight(8)
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

    def _on_provider_changed(self) -> None:
        if self._provider_combo is None or self._model_combo is None:
            return
        is_openai = self._provider_combo.currentText() == PROVIDER_LABELS.get("openai", "")
        self._model_combo.setEnabled(not is_openai)
        if self._model_hint:
            self._model_hint.setText("OpenAI uses whisper-1 (fixed)" if is_openai else "")

    def _load_devices(self) -> None:
        try:
            all_devices = AudioRecorder.list_devices()
        except Exception as exc:
            logger.warning("Failed to list audio devices: %s", exc)
            all_devices = []

        seen: set[str] = set()
        self._devices = []
        for dev in all_devices:
            if dev["name"] not in seen:
                seen.add(dev["name"])
                self._devices.append(dev)

        default_marker = ""
        try:
            import sounddevice as sd
            default_info = sd.query_devices(kind="input")
            if default_info:
                default_marker = default_info["name"]
        except Exception:
            pass

        default_entry = None
        other_entries = []
        for dev in self._devices:
            label = dev["name"]
            entry = f"{label} (#{dev['index']})"
            if label == default_marker:
                default_entry = f"* {label} [active] (#{dev['index']})"
            else:
                other_entries.append(entry)

        device_names = ["System Default"]
        if default_entry:
            device_names.append(default_entry)
        device_names.extend(other_entries)

        current = "System Default"
        if self._settings and self._settings.input_device is not None:
            for dev in self._devices:
                if dev["index"] == self._settings.input_device:
                    lbl = dev["name"]
                    current = (
                        f"* {lbl} [active] (#{dev['index']})"
                        if lbl == default_marker
                        else f"{lbl} (#{dev['index']})"
                    )
                    break

        QTimer.singleShot(0, lambda: self._update_device_dropdown(device_names, current))

    def _update_device_dropdown(self, names: list[str], current: str) -> None:
        if self._device_combo is not None:
            self._device_combo.clear()
            self._device_combo.addItems(names)
            self._device_combo.setCurrentText(current)

    def _test_hotkey(self) -> None:
        combo_label = self._hotkey_combo.currentText()
        self._hotkey_test_label.setText(f"Press {combo_label} now...")
        self._hotkey_test_label.setStyleSheet(f"color: {_ACCENT()}; font-size: 10px;")
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Testing...")
        self._testing_hotkey = True
        self._test_combo_label = combo_label
        self._test_target_keys = _combo_to_qt_keys(_preset_label_to_combo(combo_label))
        self._test_pressed_keys = set()
        self.setFocus()
        self.grabKeyboard()
        QTimer.singleShot(5000, self._finish_hotkey_test_timeout)

    def _finish_hotkey_test_ok(self) -> None:
        self._testing_hotkey = False
        self.releaseKeyboard()
        self._hotkey_test_label.setText(f"OK - {self._test_combo_label} detected!")
        self._hotkey_test_label.setStyleSheet("color: #22c55e; font-size: 10px;")
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test")

    def _finish_hotkey_test_timeout(self) -> None:
        if not self._testing_hotkey:
            return
        self._testing_hotkey = False
        self.releaseKeyboard()
        self._hotkey_test_label.setText("Not detected. Try another hotkey.")
        self._hotkey_test_label.setStyleSheet(f"color: {_DANGER()}; font-size: 10px;")
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._testing_hotkey:
            self._test_pressed_keys.add(event.key())
            if self._test_target_keys.issubset(self._test_pressed_keys):
                self._finish_hotkey_test_ok()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if self._testing_hotkey:
            self._test_pressed_keys.discard(event.key())
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _save_settings(self) -> None:
        if not self._settings:
            return

        lang_label = self._lang_combo.currentText()
        self._settings.language = LANGUAGE_OPTIONS.get(lang_label, "fr")

        provider_label = self._provider_combo.currentText()
        for code, label in PROVIDER_LABELS.items():
            if label == provider_label:
                self._settings.primary_provider = code
                break

        model_label = self._model_combo.currentText()
        for code, label in MODEL_LABELS.items():
            if label == model_label:
                self._settings.whisper_model = code
                break

        self._settings.prompt = self._prompt_text.toPlainText().strip()
        self._settings.post_process = self._post_process_cb.isChecked()

        device_label = self._device_combo.currentText()
        if device_label in ("System Default", "Loading..."):
            self._settings.input_device = None
        else:
            idx_match = re.search(r"#(\d+)\)$", device_label)
            self._settings.input_device = int(idx_match.group(1)) if idx_match else None

        mode_label = self._mode_combo.currentText()
        for code, label in RECORD_MODE_LABELS.items():
            if label == mode_label:
                self._settings.record_mode = code
                break

        hotkey_label = self._hotkey_combo.currentText()
        self._settings.hotkey = _preset_label_to_combo(hotkey_label)

        self._settings.show_notifications = self._notif_cb.isChecked()
        self._settings.restore_clipboard = self._clipboard_cb.isChecked()

        self._settings.save()
        logger.info("Settings saved from dashboard")

        if self._on_settings_save:
            self._on_settings_save(self._settings)

        if self._settings_status_label:
            self._settings_status_label.setText("Settings saved.")
            QTimer.singleShot(3000, lambda: self._settings_status_label.setText(""))

    # ---- Tab Switching ----

    def _switch_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            if i == index:
                btn.setStyleSheet(_nav_btn_active_style(_theme))
            else:
                btn.setStyleSheet(_nav_btn_style(_theme))

    def closeEvent(self, event) -> None:  # noqa: N802
        self._is_open = False
        event.accept()


# ---- Utility functions ----

def _code_to_label(code: str, mapping: dict[str, str]) -> str:
    for label, c in mapping.items():
        if c == code:
            return label
    return list(mapping.keys())[0]


def _combo_to_preset_label(combo: str) -> str:
    for code, label in HOTKEY_PRESETS.items():
        if code == combo:
            return label
    return combo.replace("<", "").replace(">", "").replace("+", " + ").title()


def _preset_label_to_combo(label: str) -> str:
    for code, lbl in HOTKEY_PRESETS.items():
        if lbl == label:
            return code
    return f"{_MOD}+<shift>+<space>"


def _combo_to_qt_keys(combo: str) -> set[int]:
    from PyQt6.QtCore import Qt as QtKey

    if _IS_MAC:
        _ctrl_key = QtKey.Key.Key_Meta
        _cmd_key = QtKey.Key.Key_Control
    else:
        _ctrl_key = QtKey.Key.Key_Control
        _cmd_key = QtKey.Key.Key_Meta

    _MAP = {
        "<ctrl>": _ctrl_key,
        "<shift>": QtKey.Key.Key_Shift,
        "<alt>": QtKey.Key.Key_Alt,
        "<cmd>": _cmd_key,
        "<space>": QtKey.Key.Key_Space,
        "<f7>": QtKey.Key.Key_F7,
        "<f8>": QtKey.Key.Key_F8,
        "<f9>": QtKey.Key.Key_F9,
        "<f10>": QtKey.Key.Key_F10,
        "<f11>": QtKey.Key.Key_F11,
        "<f12>": QtKey.Key.Key_F12,
    }

    keys: set[int] = set()
    for part in combo.split("+"):
        part = part.strip().lower()
        if part in _MAP:
            keys.add(_MAP[part].value)
        elif len(part) == 1:
            keys.add(ord(part.upper()))
    return keys
