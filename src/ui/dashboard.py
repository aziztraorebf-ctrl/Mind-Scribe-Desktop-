"""Dashboard window with sidebar navigation for MindScribe Desktop.

Provides Home (history/stats), Dictionary (vocabulary editor), and Styles
(transcription style selection) tabs in a single PyQt6 window.
"""

import logging
from datetime import datetime
from typing import Callable

import pyperclip
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
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

logger = logging.getLogger(__name__)

# Dark theme colors (matching existing windows)
BG = "#1e1e2e"
BG_SIDEBAR = "#16162a"
BG_FIELD = "#2a2a3e"
FG = "#e0e0e0"
FG_DIM = "#999999"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
DANGER = "#ef4444"

SIDEBAR_WIDTH = 160
WINDOW_W = 700
WINDOW_H = 520

_NAV_ITEMS = ["Home", "Dictionary", "Styles"]

_SIDEBAR_BUTTON_STYLE = """
QPushButton {{
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    color: {fg_dim};
    background: transparent;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {bg_field};
    color: {fg};
}}
"""

_SIDEBAR_BUTTON_ACTIVE_STYLE = """
QPushButton {{
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    color: {accent};
    background: {bg_field};
    font-size: 13px;
    font-weight: 600;
}}
"""


class _HistoryEntry(QFrame):
    """A single transcription history entry widget."""

    def __init__(self, entry: dict, on_delete: Callable, parent=None) -> None:
        super().__init__(parent)
        self._entry = entry
        self._on_delete = on_delete
        self._expanded = False

        self.setStyleSheet(
            f"QFrame {{ background: {BG_FIELD}; border-radius: 8px; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: timestamp + action buttons
        header = QHBoxLayout()
        try:
            dt = datetime.fromisoformat(entry["created_at"])
            ts_str = dt.strftime("%b %d at %-I:%M %p")
        except (ValueError, KeyError):
            ts_str = entry.get("created_at", "")
        ts_label = QLabel(ts_str)
        ts_label.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; background: transparent;")
        header.addWidget(ts_label)
        header.addStretch()

        # Action buttons (always visible for simplicity)
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(24)
        copy_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: white; border: none; "
            f"border-radius: 4px; padding: 2px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {ACCENT_HOVER}; }}"
        )
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._copy)
        header.addWidget(copy_btn)

        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(24)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: {DANGER}; color: white; border: none; "
            f"border-radius: 4px; padding: 2px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #dc2626; }}"
        )
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self._on_delete(self._entry["id"], self))
        header.addWidget(del_btn)

        layout.addLayout(header)

        # Preview text
        text = entry.get("text", "")
        preview = text[:120] + ("..." if len(text) > 120 else "")
        self._preview_label = QLabel(preview)
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(f"color: {FG}; font-size: 13px; background: transparent;")
        layout.addWidget(self._preview_label)

        # Full text (hidden by default)
        self._full_label = QLabel(text)
        self._full_label.setWordWrap(True)
        self._full_label.setStyleSheet(f"color: {FG}; font-size: 13px; background: transparent;")
        self._full_label.setVisible(False)
        layout.addWidget(self._full_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Toggle expand/collapse on click."""
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
        name_label.setStyleSheet(f"color: {FG}; font-size: 13px; font-weight: 600; background: transparent;")
        layout.addWidget(name_label)

        desc_label = QLabel(style.get("description", ""))
        desc_label.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; background: transparent;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

    def _set_active(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                f"QFrame {{ background: {BG_FIELD}; border-left: 3px solid {ACCENT}; border-radius: 6px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {BG_FIELD}; border: none; border-radius: 6px; }}"
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._on_click(self._style)
        super().mousePressEvent(event)


class Dashboard(QWidget):
    """Main dashboard window with sidebar navigation and stacked content pages."""

    _sig_open = pyqtSignal()
    _sig_raise = pyqtSignal()

    def __init__(
        self,
        history_store=None,
        style_store=None,
        vocabulary=None,
        on_style_change: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__()
        self._history_store = history_store
        self._style_store = style_store
        self._vocabulary = vocabulary
        self._on_style_change = on_style_change
        self._is_open = False
        self._nav_buttons: list[QPushButton] = []
        self._active_style_name = "Default"

        self._sig_open.connect(self._build_window)
        self._sig_raise.connect(self._raise_window)

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
        self.raise_()
        self.activateWindow()

    def _build_window(self) -> None:
        """Build the dashboard UI (lazy, called once via signal)."""
        self.setObjectName("dashboard_root")
        self.setWindowTitle("MindScribe Desktop - Dashboard")
        self.setFixedSize(WINDOW_W, WINDOW_H)
        self.setWindowFlag(Qt.WindowType.Window)
        self.setStyleSheet(f"QWidget#dashboard_root {{ background: {BG}; }}")

        # --- Main layout: sidebar + content ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"background: {BG_SIDEBAR}; border: none;")
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
        main_layout.addWidget(sidebar)

        # Stacked content area
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {BG};")

        # Build tab pages
        self._stack.addWidget(self._build_home_tab())
        self._stack.addWidget(self._build_dictionary_tab())
        self._stack.addWidget(self._build_styles_tab())

        main_layout.addWidget(self._stack)

        # Select first tab
        self._switch_tab(0)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - WINDOW_W) // 2
            y = (geo.height() - WINDOW_H) // 2
            self.move(x, y)

        self._is_open = True
        self.show()

    # ---- Home Tab (FR4) ----

    def _build_home_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Stats bar
        stats = {"streak_days": 0, "total_words": 0, "avg_wpm": 0.0}
        if self._history_store:
            try:
                stats = self._history_store.get_stats()
            except Exception:
                logger.warning("Failed to load stats")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        for label, value in [
            ("Streak", f"{stats['streak_days']} days"),
            ("Total Words", str(stats["total_words"])),
            ("Avg WPM", str(stats["avg_wpm"])),
        ]:
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background: {BG_FIELD}; border-radius: 8px; }}")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            val_lbl = QLabel(str(value))
            val_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 18px; font-weight: 700; background: transparent;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(val_lbl)
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; background: transparent;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(name_lbl)
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        # History list in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG}; border: none; }}"
        )

        self._history_container = QWidget()
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(8)

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
            empty_label.setStyleSheet(f"color: {FG_DIM}; font-size: 14px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_layout.addWidget(empty_label)

        self._history_layout.addStretch()
        scroll.setWidget(self._history_container)
        layout.addWidget(scroll)

        return page

    def _delete_entry(self, entry_id: int, widget: QWidget) -> None:
        """Delete a history entry."""
        if self._history_store:
            try:
                self._history_store.delete(entry_id)
            except Exception:
                logger.error("Failed to delete entry %d", entry_id)
                return
        widget.setParent(None)
        widget.deleteLater()

    # ---- Dictionary Tab (FR5) ----

    def _build_dictionary_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel("Personal Dictionary")
        title.setStyleSheet(f"color: {FG}; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel("One word or phrase per line. Always recognized correctly by Whisper.")
        subtitle.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._vocab_text = QTextEdit()
        self._vocab_text.setStyleSheet(
            f"QTextEdit {{ background: {BG_FIELD}; color: {FG}; border: 1px solid #3a3a50; "
            f"border-radius: 6px; padding: 8px; font-size: 13px; }}"
        )
        if self._vocabulary:
            try:
                words = self._vocabulary.words
                self._vocab_text.setPlainText("\n".join(words))
            except Exception:
                pass
        layout.addWidget(self._vocab_text)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {ACCENT_HOVER}; }}"
        )
        save_btn.clicked.connect(self._save_vocabulary)
        layout.addWidget(save_btn)

        return page

    def _save_vocabulary(self) -> None:
        """Save vocabulary words from the text edit."""
        if not self._vocabulary:
            return
        text = self._vocab_text.toPlainText()
        words = [w.strip() for w in text.split("\n") if w.strip()]
        try:
            self._vocabulary.set_words(words)
            logger.info("Vocabulary saved: %d words", len(words))
        except Exception:
            logger.error("Failed to save vocabulary")

    # ---- Styles Tab (FR6) ----

    def _build_styles_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel("Transcription Styles")
        title.setStyleSheet(f"color: {FG}; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel("Select a style to change how your dictation is formatted.")
        subtitle.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Scroll area for style cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG}; border: none; }}")

        self._styles_container = QWidget()
        self._styles_layout = QVBoxLayout(self._styles_container)
        self._styles_layout.setContentsMargins(0, 0, 0, 0)
        self._styles_layout.setSpacing(8)

        self._rebuild_style_cards()

        self._styles_layout.addStretch()
        scroll.setWidget(self._styles_container)
        layout.addWidget(scroll)

        # Add Custom Style button
        add_btn = QPushButton("+ Add Custom Style")
        add_btn.setFixedHeight(36)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_FIELD}; color: {FG}; border: 1px solid #3a3a50; "
            f"border-radius: 6px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #3a3a50; }}"
        )
        add_btn.clicked.connect(self._add_custom_style_dialog)
        layout.addWidget(add_btn)

        return page

    def _rebuild_style_cards(self) -> None:
        """Clear and rebuild style cards."""
        # Remove existing cards
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

            # Add delete button for custom styles
            if not style.get("is_builtin", True):
                del_btn = QPushButton(f"Delete '{style['name']}'")
                del_btn.setFixedHeight(24)
                del_btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {DANGER}; border: none; "
                    f"font-size: 11px; }} QPushButton:hover {{ color: #dc2626; }}"
                )
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                name = style["name"]
                del_btn.clicked.connect(lambda checked, n=name: self._delete_custom_style(n))
                self._styles_layout.addWidget(del_btn)

        self._styles_layout.addStretch()

    def _select_style(self, style: dict) -> None:
        """Handle style card click."""
        self._active_style_name = style["name"]
        if self._on_style_change:
            self._on_style_change(style["name"], style.get("prompt", ""))
        self._rebuild_style_cards()

    def _add_custom_style_dialog(self) -> None:
        """Show dialog to add a custom style."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Custom Style")
        dialog.setFixedSize(400, 300)
        dialog.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        name_label = QLabel("Style Name")
        name_label.setStyleSheet(f"color: {FG}; font-size: 12px;")
        layout.addWidget(name_label)

        name_input = QLineEdit()
        name_input.setStyleSheet(
            f"QLineEdit {{ background: {BG_FIELD}; color: {FG}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 6px; }}"
        )
        layout.addWidget(name_input)

        prompt_label = QLabel("Prompt")
        prompt_label.setStyleSheet(f"color: {FG}; font-size: 12px;")
        layout.addWidget(prompt_label)

        prompt_input = QTextEdit()
        prompt_input.setStyleSheet(
            f"QTextEdit {{ background: {BG_FIELD}; color: {FG}; border: 1px solid #3a3a50; "
            f"border-radius: 4px; padding: 6px; }}"
        )
        layout.addWidget(prompt_input)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"QPushButton {{ background: {BG_FIELD}; color: {FG}; border: none; border-radius: 4px; padding: 6px 16px; }}")
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: white; border: none; border-radius: 4px; padding: 6px 16px; }}"
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
        """Delete a custom style."""
        if self._style_store:
            try:
                self._style_store.delete_custom_style(name)
                self._rebuild_style_cards()
            except ValueError as e:
                logger.warning("Cannot delete style: %s", e)

    # ---- Tab Switching ----

    def _switch_tab(self, index: int) -> None:
        """Switch the active sidebar tab."""
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            if i == index:
                btn.setStyleSheet(
                    _SIDEBAR_BUTTON_ACTIVE_STYLE.format(accent=ACCENT, bg_field=BG_FIELD)
                )
            else:
                btn.setStyleSheet(
                    _SIDEBAR_BUTTON_STYLE.format(fg_dim=FG_DIM, bg_field=BG_FIELD, fg=FG)
                )

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle window close."""
        self._is_open = False
        event.accept()
