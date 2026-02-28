"""Transcription history window using PyQt6."""

import logging
import platform
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_UI_FONT = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
_MONO_FONT = "Menlo" if platform.system() == "Darwin" else "Consolas"

BG = "#1e1e2e"
BG_FIELD = "#2a2a3e"
FG = "#e0e0e0"
FG_DIM = "#999999"
ACCENT = "#3b82f6"

_STYLESHEET = """
QWidget#history_root {
    background-color: %(bg)s;
}
QListWidget {
    background-color: %(bg_field)s;
    color: %(fg)s;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px;
}
QListWidget::item {
    padding: 6px 4px;
    border-bottom: 1px solid #333;
}
QListWidget::item:selected {
    background-color: %(accent)s;
    color: white;
}
QTextEdit {
    background-color: %(bg_field)s;
    color: %(fg)s;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 6px;
}
QLabel {
    color: %(fg)s;
    background: transparent;
}
""" % {"bg": BG, "bg_field": BG_FIELD, "fg": FG, "accent": ACCENT}


class HistoryEntry:
    """A single transcription history entry."""

    def __init__(self, text: str, timestamp: datetime | None = None) -> None:
        self.text = text
        self.timestamp = timestamp or datetime.now()

    @property
    def preview(self) -> str:
        first_line = self.text.split("\n")[0][:80]
        return first_line + ("..." if len(self.text) > 80 else "")

    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


class HistoryWindow(QWidget):
    """Window that displays past transcriptions from the current session."""

    _sig_open = pyqtSignal()
    _sig_raise = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._is_open = False
        self._entries: list[HistoryEntry] = []

        self._list: QListWidget | None = None
        self._detail: QTextEdit | None = None
        self._count_label: QLabel | None = None

        self._sig_open.connect(self._build_window)
        self._sig_raise.connect(self._raise_window)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def add_entry(self, text: str) -> None:
        """Add a new transcription to history."""
        self._entries.insert(0, HistoryEntry(text))
        if self._is_open and self._list is not None:
            self._refresh_list()

    def open(self) -> None:
        """Open the history window (thread-safe)."""
        if self._is_open:
            self._sig_raise.emit()
            return
        self._sig_open.emit()

    def _raise_window(self) -> None:
        self.raise_()
        self.activateWindow()

    def _build_window(self) -> None:
        if self._is_open:
            return
        self._is_open = True

        self.setWindowTitle("MindScribe - Transcription History")
        self.setObjectName("history_root")
        self.setFixedSize(600, 450)
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(_STYLESHEET)

        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                (geo.width() - 600) // 2 + geo.x(),
                (geo.height() - 450) // 2 + geo.y(),
            )

        if self.layout() is not None:
            QWidget().setLayout(self.layout())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("Transcription History")
        title.setFont(QFont(_UI_FONT, 14, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()
        self._count_label = QLabel("")
        self._count_label.setFont(QFont(_UI_FONT, 10))
        self._count_label.setStyleSheet("color: %s;" % FG_DIM)
        header.addWidget(self._count_label)
        main_layout.addLayout(header)

        # List of entries
        self._list = QListWidget()
        self._list.setFont(QFont(_UI_FONT, 10))
        self._list.currentRowChanged.connect(self._on_selection_changed)
        main_layout.addWidget(self._list)

        # Detail view
        self._detail = QTextEdit()
        self._detail.setFont(QFont(_MONO_FONT, 11))
        self._detail.setReadOnly(True)
        self._detail.setFixedHeight(120)
        self._detail.setPlaceholderText("Select an entry above to see the full text.")
        main_layout.addWidget(self._detail)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_btn = QPushButton("  Copy Text  ")
        copy_btn.setFont(QFont(_UI_FONT, 10))
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            "QPushButton { background-color: %s; color: white; border: none;"
            " padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2563eb; }" % ACCENT
        )
        copy_btn.clicked.connect(self._copy_selected)
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("  Close  ")
        close_btn.setFont(QFont(_UI_FONT, 10))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: #ccc; border: none;"
            " padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #666; }"
        )
        close_btn.clicked.connect(self._on_close)
        btn_row.addWidget(close_btn)
        main_layout.addLayout(btn_row)

        self._refresh_list()
        self.show()
        logger.info("History window opened (%d entries)", len(self._entries))

    def _refresh_list(self) -> None:
        if self._list is None:
            return
        self._list.clear()
        for entry in self._entries:
            item = QListWidgetItem(f"[{entry.time_str}]  {entry.preview}")
            self._list.addItem(item)
        if self._count_label is not None:
            n = len(self._entries)
            self._count_label.setText(
                f"{n} transcription{'s' if n != 1 else ''}"
            )
        if not self._entries and self._detail is not None:
            self._detail.setPlainText("")

    def _on_selection_changed(self, row: int) -> None:
        if self._detail is None or row < 0 or row >= len(self._entries):
            return
        self._detail.setPlainText(self._entries[row].text)

    def _copy_selected(self) -> None:
        if self._list is None or self._detail is None:
            return
        row = self._list.currentRow()
        if 0 <= row < len(self._entries):
            import pyperclip
            pyperclip.copy(self._entries[row].text)
            logger.info("Copied transcription #%d to clipboard", row + 1)

    def _on_close(self) -> None:
        self._is_open = False
        self.hide()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._on_close()
        event.accept()
