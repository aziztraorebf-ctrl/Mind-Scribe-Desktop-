"""Global hotkey management using pynput.

Supports two modes:
- Toggle: press hotkey to start, press again to stop
- Hold: hold hotkey to record, release to stop
"""

import logging
import platform
import threading
import time
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)

# Minimum hold duration (seconds) to avoid accidental triggers on quick taps
_MIN_HOLD_DURATION = 0.3


def _parse_hotkey_keys(combo: str) -> set[str]:
    """Parse a pynput hotkey string into a set of key identifiers."""
    parts = combo.split("+")
    keys = set()
    for part in parts:
        part = part.strip().lower()
        keys.add(part)
    return keys


def _pynput_key_to_id(key) -> str:
    """Convert a pynput key event to a comparable string identifier."""
    if isinstance(key, keyboard.Key):
        return f"<{key.name}>"
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char.lower()
        if key.vk is not None:
            # Space key comes as vk=32
            if key.vk == 32:
                return "<space>"
    return ""


class HotkeyManager:
    """Manages global keyboard shortcuts for recording control.

    Supports toggle mode (press to start/stop) and hold mode
    (hold to record, release to stop).
    """

    def __init__(
        self,
        on_toggle: Callable[[], None] | None = None,
        on_hold_start: Callable[[], None] | None = None,
        on_hold_stop: Callable[[], None] | None = None,
        hotkey_combo: str = "<ctrl>+<shift>+<space>",
        mode: str = "toggle",
    ):
        self._on_toggle = on_toggle
        self._on_hold_start = on_hold_start
        self._on_hold_stop = on_hold_stop
        self._hotkey_combo = hotkey_combo
        self._mode = mode  # "toggle" or "hold"
        self._listener: keyboard.Listener | keyboard.GlobalHotKeys | None = None
        self._running = False

        # Hold mode state
        self._hotkey_keys = _parse_hotkey_keys(hotkey_combo)
        self._pressed_keys: set[str] = set()
        self._holding = False
        self._hold_start_time: float = 0.0

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("toggle", "hold"):
            return
        was_running = self._running
        self.stop()
        self._mode = value
        if was_running:
            self.start()

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
        """Start listening for the global hotkey."""
        if self._running:
            return

        if self._mode == "hold":
            # Hold mode uses a raw Listener to detect press and release
            self._pressed_keys.clear()
            self._holding = False
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._listener.daemon = True
            self._listener.start()
        else:
            # Toggle mode uses GlobalHotKeys
            self._listener = keyboard.GlobalHotKeys({
                self._hotkey_combo: self._handle_toggle,
            })
            self._listener.daemon = True
            self._listener.start()

        self._running = True
        logger.info("Hotkey listener started: %s (mode=%s)", self.hotkey_display, self._mode)

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._running = False
        self._holding = False
        self._pressed_keys.clear()
        logger.info("Hotkey listener stopped")

    def update_hotkey(self, new_combo: str) -> None:
        """Change the hotkey combination. Restarts the listener."""
        was_running = self._running
        self.stop()
        self._hotkey_combo = new_combo
        self._hotkey_keys = _parse_hotkey_keys(new_combo)
        if was_running:
            self.start()

    # -- Toggle mode --

    def _handle_toggle(self) -> None:
        """Called when the hotkey combination is pressed in toggle mode."""
        logger.debug("Hotkey triggered (toggle): %s", self.hotkey_display)
        if self._on_toggle:
            threading.Thread(target=self._on_toggle, daemon=True).start()

    # -- Hold mode --

    def _on_key_press(self, key) -> None:
        """Track pressed keys for hold mode."""
        key_id = _pynput_key_to_id(key)
        if not key_id:
            return
        self._pressed_keys.add(key_id)

        # Check if all hotkey keys are held down
        if not self._holding and self._hotkey_keys.issubset(self._pressed_keys):
            self._holding = True
            self._hold_start_time = time.monotonic()
            logger.debug("Hold started: %s", self.hotkey_display)
            if self._on_hold_start:
                threading.Thread(target=self._on_hold_start, daemon=True).start()

    def _on_key_release(self, key) -> None:
        """Detect hotkey release for hold mode."""
        key_id = _pynput_key_to_id(key)
        if not key_id:
            return
        self._pressed_keys.discard(key_id)

        # If any hotkey key is released while holding, stop
        if self._holding and key_id in self._hotkey_keys:
            held_duration = time.monotonic() - self._hold_start_time
            self._holding = False
            if held_duration >= _MIN_HOLD_DURATION:
                logger.debug("Hold released after %.1fs: %s", held_duration, self.hotkey_display)
                if self._on_hold_stop:
                    threading.Thread(target=self._on_hold_stop, daemon=True).start()
            else:
                logger.debug("Hold too short (%.2fs), ignored", held_duration)

    @staticmethod
    def default_hotkey() -> str:
        """Return the platform-appropriate default hotkey."""
        if platform.system() == "Darwin":
            return "<cmd>+<shift>+<space>"
        return "<ctrl>+<shift>+<space>"
