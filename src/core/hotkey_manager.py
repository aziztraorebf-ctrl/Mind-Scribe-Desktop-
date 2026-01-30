"""Global hotkey management using pynput."""

import logging
import platform
import threading
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyManager:
    """Manages global keyboard shortcuts for recording control."""

    def __init__(
        self,
        on_toggle: Callable[[], None] | None = None,
        hotkey_combo: str = "<ctrl>+<shift>+<space>",
    ):
        self._on_toggle = on_toggle
        self._hotkey_combo = hotkey_combo
        self._listener: keyboard.GlobalHotKeys | None = None
        self._running = False

    @property
    def hotkey_display(self) -> str:
        """Human-readable hotkey string."""
        combo = self._hotkey_combo
        combo = combo.replace("<ctrl>", "Ctrl")
        combo = combo.replace("<cmd>", "Cmd")
        combo = combo.replace("<shift>", "Shift")
        combo = combo.replace("<space>", "Space")
        combo = combo.replace("<alt>", "Alt")
        combo = combo.replace("+", " + ")
        return combo

    def start(self) -> None:
        """Start listening for the global hotkey in a background thread."""
        if self._running:
            return

        self._listener = keyboard.GlobalHotKeys({
            self._hotkey_combo: self._handle_hotkey,
        })
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        logger.info("Hotkey listener started: %s", self.hotkey_display)

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._running = False
        logger.info("Hotkey listener stopped")

    def update_hotkey(self, new_combo: str) -> None:
        """Change the hotkey combination. Restarts the listener."""
        was_running = self._running
        self.stop()
        self._hotkey_combo = new_combo
        if was_running:
            self.start()

    def _handle_hotkey(self) -> None:
        """Called when the hotkey combination is pressed."""
        logger.debug("Hotkey triggered: %s", self.hotkey_display)
        if self._on_toggle:
            # Run callback in a separate thread to avoid blocking the listener
            threading.Thread(target=self._on_toggle, daemon=True).start()

    @staticmethod
    def default_hotkey() -> str:
        """Return the platform-appropriate default hotkey."""
        if platform.system() == "Darwin":
            return "<cmd>+<shift>+<space>"
        return "<ctrl>+<shift>+<space>"
