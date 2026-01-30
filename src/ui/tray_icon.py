"""System tray icon with state indicators and context menu."""

import logging
import threading
from typing import Callable

import pystray
from pystray import MenuItem as Item

from src.ui.icons import icon_idle, icon_recording, icon_transcribing

logger = logging.getLogger(__name__)


class TrayIcon:
    """System tray icon that reflects app state and provides a context menu."""

    def __init__(
        self,
        on_toggle: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        hotkey_display: str = "Ctrl + Shift + Space",
    ):
        self._on_toggle = on_toggle
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._hotkey_display = hotkey_display
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        menu = pystray.Menu(
            Item(
                f"Toggle Recording ({self._hotkey_display})",
                self._handle_toggle,
                default=True,  # Double-click action
            ),
            Item("---", None),  # Separator
            Item("Settings", self._handle_settings),
            Item("---", None),
            Item("Quit", self._handle_quit),
        )

        self._icon = pystray.Icon(
            name="MindScribe Desktop",
            icon=icon_idle(),
            title="MindScribe Desktop - Ready",
            menu=menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("Tray icon started")

    def stop(self) -> None:
        """Remove the tray icon."""
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
        logger.info("Tray icon stopped")

    def set_idle(self) -> None:
        """Switch to idle state (gray icon)."""
        if self._icon:
            self._icon.icon = icon_idle()
            self._icon.title = "MindScribe Desktop - Ready"

    def set_recording(self) -> None:
        """Switch to recording state (red icon)."""
        if self._icon:
            self._icon.icon = icon_recording()
            self._icon.title = "MindScribe Desktop - Recording..."

    def set_transcribing(self) -> None:
        """Switch to transcribing state (amber icon)."""
        if self._icon:
            self._icon.icon = icon_transcribing()
            self._icon.title = "MindScribe Desktop - Transcribing..."

    def _handle_toggle(self, icon, item) -> None:
        if self._on_toggle:
            threading.Thread(target=self._on_toggle, daemon=True).start()

    def _handle_settings(self, icon, item) -> None:
        if self._on_settings:
            threading.Thread(target=self._on_settings, daemon=True).start()

    def _handle_quit(self, icon, item) -> None:
        if self._on_quit:
            self._on_quit()
