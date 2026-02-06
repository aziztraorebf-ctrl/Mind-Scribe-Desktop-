"""Floating overlay window that shows recording/transcribing status with animation.

PyQt6 version for macOS compatibility. Replaces the tkinter overlay.
"""

import logging
import math
import platform
import threading
from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# OS-adaptive UI fonts
_UI_FONT = ".AppleSystemUIFont" if platform.system() == "Darwin" else "Segoe UI"
_MONO_FONT = "SF Mono" if platform.system() == "Darwin" else "Consolas"

# Overlay dimensions
WINDOW_WIDTH = 300
WINDOW_HEIGHT_RECORDING = 110
WINDOW_HEIGHT_TRANSCRIBING = 70
WINDOW_WIDTH_READY = 400
WINDOW_HEIGHT_READY = 70
READY_DISPLAY_MS = 10_000  # Auto-hide after 10 seconds
FADE_DURATION_MS = 500
CANVAS_HEIGHT = 36
BAR_COUNT = 32
BAR_WIDTH = 4
BAR_GAP = 2

# Colors
BG_COLOR = "#1a1a2e"
TEXT_COLOR = "#e0e0e0"
RED_ACCENT = "#ff4444"
AMBER_ACCENT = "#ffaa00"
BTN_BG = "#2a2a4a"
BTN_HOVER = "#3a3a5a"
BTN_RED = "#cc3333"
BTN_RED_HOVER = "#ee4444"
PAUSE_COLOR = "#ffaa00"
PAUSE_HOVER = "#ffcc44"
GREEN_ACCENT = "#22c55e"


class _WaveformWidget(QWidget):
    """Custom widget that draws audio waveform bars or pulsing dots."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(CANVAS_HEIGHT)
        self._levels: list[float] = []
        self._anim_phase: float = 0.0
        self._mode: str = "recording"

    def set_data(self, levels: list[float], phase: float, mode: str) -> None:
        self._levels = levels
        self._anim_phase = phase
        self._mode = mode
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()

        if self._mode in ("recording", "paused"):
            self._draw_waveform(painter, w)
        elif self._mode == "transcribing":
            self._draw_pulse_dots(painter, w)

        painter.end()

    def _draw_waveform(self, painter: QPainter, canvas_w: int) -> None:
        total_bars_width = BAR_COUNT * (BAR_WIDTH + BAR_GAP)
        offset_x = (canvas_w - total_bars_width) // 2

        levels = self._levels
        if len(levels) < BAR_COUNT:
            levels = [0.0] * (BAR_COUNT - len(levels)) + levels

        dim_factor = 0.3 if self._mode == "paused" else 1.0

        for i in range(BAR_COUNT):
            raw_level = levels[i] if i < len(levels) else 0.0
            wave_mod = math.sin(self._anim_phase * 0.5 + i * 0.3) * 0.05
            height_ratio = max(0.06, min(1.0, raw_level + wave_mod)) * dim_factor

            bar_h = int(height_ratio * (CANVAS_HEIGHT - 4))
            x1 = offset_x + i * (BAR_WIDTH + BAR_GAP)
            y_center = CANVAS_HEIGHT // 2
            y1 = y_center - bar_h // 2

            intensity = int(80 + height_ratio * 175)
            painter.fillRect(x1, y1, BAR_WIDTH, bar_h, QColor(intensity, 0x22, 0x22))

    def _draw_pulse_dots(self, painter: QPainter, canvas_w: int) -> None:
        dot_count = 3
        dot_radius_base = 5
        spacing = 30
        total_w = dot_count * spacing
        offset_x = (canvas_w - total_w) // 2
        y_center = CANVAS_HEIGHT // 2

        for i in range(dot_count):
            phase = self._anim_phase - i * 0.5
            scale = (math.sin(phase) + 1) / 2
            r = dot_radius_base + int(scale * 4)
            alpha_int = int(120 + scale * 135)

            cx = offset_x + i * spacing + spacing // 2
            painter.setBrush(QBrush(QColor(alpha_int, int(alpha_int * 0.65), 0)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx, y_center), r, r)


class RecordingOverlay(QWidget):
    """Floating overlay with reactive waveform, timer, and control buttons.

    Thread-safe: all public methods can be called from any thread.
    UI updates are marshalled to the main thread via Qt signals.
    """

    # Signals for thread-safe UI updates (emitted from any thread)
    _sig_show = pyqtSignal(str)
    _sig_hide = pyqtSignal()
    _sig_show_ready = pyqtSignal(str)
    _sig_stop = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode: str = "idle"
        self._anim_phase: float = 0.0
        self._ready_hotkey: str = ""

        # Audio level data source (set by app.py)
        self._get_levels: Callable[[], list[float]] | None = None
        self._get_duration: Callable[[], float] | None = None

        # Action callbacks (set by app.py)
        self.on_stop: Callable[[], None] | None = None
        self.on_cancel: Callable[[], None] | None = None
        self.on_pause: Callable[[], None] | None = None

        self._current_fade: QPropertyAnimation | None = None

        self._setup_ui()
        self._connect_signals()
        self._setup_animation()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT_RECORDING)

        # Main layout wraps a styled container
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._container = QFrame(self)
        self._container.setObjectName("overlay_bg")
        self._container.setStyleSheet(
            "#overlay_bg { background-color: %s; border-radius: 8px; }" % BG_COLOR
        )
        root_layout.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # -- Top row: status + timer --
        top = QHBoxLayout()
        self._status_label = QLabel("")
        self._status_label.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
        self._status_label.setStyleSheet("color: %s;" % TEXT_COLOR)

        self._timer_label = QLabel("00:00")
        self._timer_label.setFont(QFont(_MONO_FONT, 11))
        self._timer_label.setStyleSheet("color: %s;" % TEXT_COLOR)
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        top.addWidget(self._status_label)
        top.addStretch()
        top.addWidget(self._timer_label)
        layout.addLayout(top)

        # -- Waveform --
        self._waveform = _WaveformWidget()
        self._waveform.setStyleSheet("background: transparent;")
        layout.addWidget(self._waveform)

        # -- Button row --
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_pause = self._make_button("Pause", PAUSE_COLOR, PAUSE_HOVER)
        self._btn_pause.clicked.connect(self._handle_pause)

        self._btn_stop = self._make_button("Stop", BTN_RED, BTN_RED_HOVER)
        self._btn_stop.clicked.connect(self._handle_stop)

        self._btn_cancel = self._make_button("Cancel", BTN_BG, BTN_HOVER, fg="#999999")
        self._btn_cancel.clicked.connect(self._handle_cancel)

        btn_row.addWidget(self._btn_pause)
        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addStretch()

        self._btn_container = QWidget()
        self._btn_container.setLayout(btn_row)
        self._btn_container.setStyleSheet("background: transparent;")
        layout.addWidget(self._btn_container)

        # Opacity effect for fade-in / fade-out
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.92)
        self.setGraphicsEffect(self._opacity)

        # Drag support
        self._drag_pos: QPoint | None = None

    @staticmethod
    def _make_button(text: str, bg: str, hover: str, fg: str = "#ffffff") -> QPushButton:
        btn = QPushButton(f"  {text}  ")
        btn.setFont(QFont(_UI_FONT, 9))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: %s; color: %s; border: none;"
            " padding: 4px 8px; border-radius: 3px; }"
            "QPushButton:hover { background-color: %s; }" % (bg, fg, hover)
        )
        return btn

    def _connect_signals(self) -> None:
        self._sig_show.connect(self._show_window)
        self._sig_hide.connect(self._hide_window)
        self._sig_show_ready.connect(self._show_ready_window)
        self._sig_stop.connect(self._stop_impl)

    def _setup_animation(self) -> None:
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)

    # ------------------------------------------------------------------
    # Public API (thread-safe — can be called from any thread)
    # ------------------------------------------------------------------

    def set_audio_source(
        self,
        get_levels: Callable[[], list[float]],
        get_duration: Callable[[], float],
    ) -> None:
        self._get_levels = get_levels
        self._get_duration = get_duration

    def start(self) -> None:
        """Initialise the overlay (widgets already created by __init__)."""
        self._anim_timer.start(33)  # ~30 fps
        logger.info("Recording overlay initialized")

    def stop(self) -> None:
        """Destroy the overlay (thread-safe)."""
        self._sig_stop.emit()

    def _stop_impl(self) -> None:
        """Actual stop — runs on Qt main thread."""
        self._anim_timer.stop()
        self.close()

    def show_recording(self) -> None:
        self._mode = "recording"
        self._sig_show.emit("recording")

    def show_paused(self) -> None:
        self._mode = "paused"
        self._sig_show.emit("paused")

    def show_transcribing(self) -> None:
        self._mode = "transcribing"
        self._sig_show.emit("transcribing")

    def show_ready(self, hotkey_display: str) -> None:
        self._mode = "ready"
        self._ready_hotkey = hotkey_display
        self._sig_show_ready.emit(hotkey_display)

    def hide(self) -> None:
        self._mode = "idle"
        self._sig_hide.emit()

    # ------------------------------------------------------------------
    # Slot implementations (run on the main / Qt thread)
    # ------------------------------------------------------------------

    def _show_window(self, mode: str) -> None:
        current_pos = self.pos()

        if mode == "recording":
            self._status_label.setText("Recording")
            self._status_label.setStyleSheet("color: %s;" % RED_ACCENT)
            self._status_label.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
            self._timer_label.setFont(QFont(_MONO_FONT, 11))
            self._timer_label.show()
            self._waveform.show()
            self._btn_container.show()
            self._btn_pause.setText("  Pause  ")
            self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT_RECORDING)
            if current_pos.x() > 0:
                self.move(current_pos)
            else:
                self._center_top()

        elif mode == "paused":
            self._status_label.setText("Paused")
            self._status_label.setStyleSheet("color: %s;" % AMBER_ACCENT)
            self._btn_pause.setText("  Resume  ")

        elif mode == "transcribing":
            self._status_label.setText("Transcribing...")
            self._status_label.setStyleSheet("color: %s;" % AMBER_ACCENT)
            self._timer_label.setText("")
            self._waveform.hide()
            self._btn_container.hide()
            self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT_TRANSCRIBING)
            if current_pos.x() > 0:
                self.move(current_pos)

        self.show()
        self.raise_()

    def _show_ready_window(self, hotkey_display: str) -> None:
        self._status_label.setText("MindScribe Ready")
        self._status_label.setStyleSheet("color: %s;" % GREEN_ACCENT)
        self._status_label.setFont(QFont(_UI_FONT, 13, QFont.Weight.Bold))

        self._timer_label.setText(hotkey_display)
        self._timer_label.setFont(QFont(_MONO_FONT, 13))
        self._timer_label.show()

        self._waveform.hide()
        self._btn_container.hide()

        self.setFixedSize(WINDOW_WIDTH_READY, WINDOW_HEIGHT_READY)

        # Center on screen
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = (geo.width() - WINDOW_WIDTH_READY) // 2 + geo.x()
            y = (geo.height() - WINDOW_HEIGHT_READY) // 2 + geo.y()
            self.move(x, y)

        # Fade in
        self._opacity.setOpacity(0.0)
        self._fade_in()
        self.show()
        self.raise_()

        # Auto-hide after timeout
        QTimer.singleShot(READY_DISPLAY_MS, self._auto_hide_ready)

    def _hide_window(self) -> None:
        super().hide()

    def _center_top(self) -> None:
        """Position overlay at top-center of screen."""
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            self.move(x, geo.y() + 18)

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _animate(self) -> None:
        if self._mode in ("recording", "paused"):
            levels = self._get_levels() if self._get_levels else []
            self._waveform.set_data(levels, self._anim_phase, self._mode)
            self._update_timer()
        elif self._mode == "transcribing":
            self._waveform.set_data([], self._anim_phase, "transcribing")
        elif self._mode == "ready":
            self._pulse_ready_text()

        self._anim_phase += 0.15

    def _update_timer(self) -> None:
        if not self._get_duration:
            return
        secs = self._get_duration()
        minutes = int(secs) // 60
        seconds = int(secs) % 60
        self._timer_label.setText(f"{minutes:02d}:{seconds:02d}")

    def _pulse_ready_text(self) -> None:
        pulse = (math.sin(self._anim_phase * 1.5) + 1) / 2
        r = int(0x22 + pulse * (0x66 - 0x22))
        g = int(0x80 + pulse * (0xFF - 0x80))
        b = int(0x3E + pulse * (0x7E - 0x3E))
        self._status_label.setStyleSheet("color: #%02x%02x%02x;" % (r, g, b))

    # ------------------------------------------------------------------
    # Fade helpers
    # ------------------------------------------------------------------

    def _fade_in(self) -> None:
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(FADE_DURATION_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(0.92)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.start()
        self._current_fade = anim  # prevent GC

    def _fade_out(self, on_finished: Callable | None = None) -> None:
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(FADE_DURATION_MS)
        anim.setStartValue(self._opacity.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        if on_finished:
            anim.finished.connect(on_finished)
        anim.start()
        self._current_fade = anim

    def _auto_hide_ready(self) -> None:
        if self._mode == "ready":
            self._fade_out(on_finished=self._finish_auto_hide)

    def _finish_auto_hide(self) -> None:
        self._mode = "idle"
        self._opacity.setOpacity(0.92)
        # Restore normal fonts
        self._status_label.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
        self._timer_label.setFont(QFont(_MONO_FONT, 11))
        self._hide_window()

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _handle_stop(self) -> None:
        if self.on_stop:
            threading.Thread(target=self.on_stop, daemon=True).start()

    def _handle_cancel(self) -> None:
        if self.on_cancel:
            threading.Thread(target=self.on_cancel, daemon=True).start()

    def _handle_pause(self) -> None:
        if self.on_pause:
            threading.Thread(target=self.on_pause, daemon=True).start()

    # ------------------------------------------------------------------
    # Dragging
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None
