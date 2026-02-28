"""System tray icon using PyQt6 QSystemTrayIcon.

Replaces the pystray-based tray icon to avoid macOS SIGTRAP crashes.
pystray runs AppKit on a daemon thread which conflicts with PyQt6's
Cocoa event loop; QSystemTrayIcon integrates natively with Qt.
"""

import io
import logging

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from src.ui.icons import icon_idle, icon_recording, icon_transcribing

logger = logging.getLogger(__name__)


def _pil_to_qicon(pil_image) -> QIcon:
    """Convert a Pillow Image to a QIcon."""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    qimage = QImage()
    qimage.loadFromData(buf.getvalue())
    return QIcon(QPixmap.fromImage(qimage))


class TrayIcon:
    """System tray icon that reflects app state and provides a context menu.

    All methods are safe to call from any thread — calls that touch Qt
    widgets are automatically marshalled to the main thread via
    QTimer.singleShot.
    """

    def __init__(
        self,
        on_toggle=None,
        on_settings=None,
        on_history=None,
        on_dashboard=None,
        on_quit=None,
        hotkey_display: str = "Ctrl + Shift + Space",
    ):
        self._on_toggle = on_toggle
        self._on_settings = on_settings
        self._on_history = on_history
        self._on_dashboard = on_dashboard
        self._on_quit = on_quit
        self._hotkey_display = hotkey_display
        self._active_style = "Default"
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._toggle_action: QAction | None = None

    def start(self) -> None:
        """Create and show the tray icon."""
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_pil_to_qicon(icon_idle()))
        self._tray.setToolTip("MindScribe Desktop - Ready")

        self._build_menu()

        self._tray.activated.connect(self._on_activated)
        self._tray.show()
        logger.info("Tray icon started")

    def _build_menu(self) -> None:
        """Build (or rebuild) the context menu."""
        self._menu = QMenu()

        self._toggle_action = QAction(
            f"Toggle Recording ({self._hotkey_display})", self._menu
        )
        self._toggle_action.triggered.connect(self._handle_toggle)
        self._menu.addAction(self._toggle_action)

        self._menu.addSeparator()

        dashboard_action = QAction("Dashboard", self._menu)
        dashboard_action.triggered.connect(self._handle_dashboard)
        self._menu.addAction(dashboard_action)

        self._style_action = QAction(f"Style: {self._active_style}", self._menu)
        self._style_action.setEnabled(False)
        self._menu.addAction(self._style_action)

        self._menu.addSeparator()

        settings_action = QAction("Settings", self._menu)
        settings_action.triggered.connect(self._handle_settings)
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        quit_action = QAction("Quit", self._menu)
        quit_action.triggered.connect(self._handle_quit)
        self._menu.addAction(quit_action)

        if self._tray is not None:
            self._tray.setContextMenu(self._menu)

    def stop(self) -> None:
        """Remove the tray icon."""
        if self._tray is not None:
            self._tray.hide()
            self._tray = None
        logger.info("Tray icon stopped")

    # ------------------------------------------------------------------
    # State changes (thread-safe via QTimer.singleShot)
    # ------------------------------------------------------------------

    def set_idle(self) -> None:
        """Switch to idle state (gray icon)."""
        QTimer.singleShot(0, self._apply_idle)

    def _apply_idle(self) -> None:
        if self._tray:
            self._tray.setIcon(_pil_to_qicon(icon_idle()))
            self._tray.setToolTip("MindScribe Desktop - Ready")

    def set_recording(self) -> None:
        """Switch to recording state (red icon)."""
        QTimer.singleShot(0, self._apply_recording)

    def _apply_recording(self) -> None:
        if self._tray:
            self._tray.setIcon(_pil_to_qicon(icon_recording()))
            self._tray.setToolTip("MindScribe Desktop - Recording...")

    def set_transcribing(self) -> None:
        """Switch to transcribing state (amber icon)."""
        QTimer.singleShot(0, self._apply_transcribing)

    def _apply_transcribing(self) -> None:
        if self._tray:
            self._tray.setIcon(_pil_to_qicon(icon_transcribing()))
            self._tray.setToolTip("MindScribe Desktop - Transcribing...")

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _on_activated(self, reason) -> None:
        """Handle tray icon double-click (toggle recording)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._handle_toggle()

    def _handle_toggle(self) -> None:
        if self._on_toggle:
            self._on_toggle()

    def _handle_settings(self) -> None:
        if self._on_settings:
            self._on_settings()

    def _handle_history(self) -> None:
        if self._on_history:
            self._on_history()

    def _handle_dashboard(self) -> None:
        if self._on_dashboard:
            self._on_dashboard()

    def _handle_quit(self) -> None:
        if self._on_quit:
            self._on_quit()

    def update_hotkey_display(self, new_display: str) -> None:
        """Rebuild the tray menu with an updated hotkey display string."""
        self._hotkey_display = new_display
        QTimer.singleShot(0, self._build_menu)

    def update_style_display(self, style_name: str) -> None:
        """Update the active style shown in the tray menu."""
        self._active_style = style_name
        QTimer.singleShot(0, self._build_menu)
