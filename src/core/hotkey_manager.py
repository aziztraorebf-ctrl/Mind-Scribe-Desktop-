"""Global hotkey management.

Uses Quartz CGEventTap on macOS (avoids pynput SIGTRAP crash from
TSMGetInputSourceProperty on background thread) and pynput
keyboard.Listener on other platforms.

Supports two modes:
- Toggle: press hotkey to start, press again to stop
- Hold: hold hotkey to record, release to stop
"""

import logging
import platform
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_IS_MACOS = platform.system() == "Darwin"

if not _IS_MACOS:
    from pynput import keyboard

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


_MODIFIER_NORMALIZE = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
}


def _pynput_key_to_id(key) -> str:
    """Convert a pynput key event to a comparable string identifier.

    Only used on non-macOS platforms where pynput is the backend.
    """
    if isinstance(key, keyboard.Key):
        name = _MODIFIER_NORMALIZE.get(key.name, key.name)
        return f"<{name}>"
    if isinstance(key, keyboard.KeyCode):
        if key.vk is not None:
            if key.vk == 32:
                return "<space>"
            if key.vk == 107:
                return "<numpad_plus>"
        if key.char:
            return key.char.lower()
    return ""


def _format_hotkey_display(combo: str) -> str:
    """Format a pynput combo string for human-readable display."""
    return combo.replace("<", "").replace(">", "").replace("+", " + ").title()


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
        self._listener = None  # QuartzHotkeyListener or pynput Listener
        self._running = False

        # Key tracking state (shared by both modes)
        self._hotkey_keys = _parse_hotkey_keys(hotkey_combo)
        self._pressed_keys: set[str] = set()
        self._holding = False
        self._hold_start_time: float = 0.0
        self._toggle_pressed = False

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("toggle", "hold") or value == self._mode:
            return
        was_running = self._running
        self.stop()
        self._mode = value
        if was_running:
            self.start()

    @property
    def hotkey_display(self) -> str:
        """Human-readable hotkey string."""
        return _format_hotkey_display(self._hotkey_combo)

    def start(self) -> None:
        """Start listening for the global hotkey."""
        if self._running:
            return

        try:
            self._pressed_keys.clear()
            self._holding = False
            self._toggle_pressed = False

            if _IS_MACOS:
                self._start_quartz()
            else:
                self._start_pynput()

            self._running = True
            logger.info(
                "Hotkey listener started: %s (mode=%s)",
                self.hotkey_display,
                self._mode,
            )

        except Exception as exc:
            logger.error(
                "Failed to start hotkey listener for '%s': %s",
                self._hotkey_combo,
                exc,
            )
            self._listener = None
            self._running = False
            self._try_fallback()

    def _start_quartz(self) -> None:
        """Start macOS Quartz CGEventTap listener."""
        from src.core.quartz_hotkey import QuartzHotkeyListener

        self._listener = QuartzHotkeyListener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.start()

    def _start_pynput(self) -> None:
        """Start pynput keyboard Listener (non-macOS)."""
        self._listener = keyboard.Listener(
            on_press=self._on_pynput_press,
            on_release=self._on_pynput_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def _try_fallback(self) -> None:
        """Fall back to default hotkey if the current one failed."""
        default = self.default_hotkey()
        if self._hotkey_combo != default:
            logger.info("Falling back to default hotkey: %s", default)
            self._hotkey_combo = default
            self._hotkey_keys = _parse_hotkey_keys(default)
            try:
                self._pressed_keys.clear()
                self._holding = False
                self._toggle_pressed = False

                if _IS_MACOS:
                    self._start_quartz()
                else:
                    self._start_pynput()

                self._running = True
                logger.info(
                    "Hotkey listener started with fallback: %s",
                    self.hotkey_display,
                )
            except Exception as fallback_exc:
                logger.error("Fallback hotkey also failed: %s", fallback_exc)
                self._listener = None
                self._running = False

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._running = False
        self._holding = False
        self._toggle_pressed = False
        self._pressed_keys.clear()
        logger.info("Hotkey listener stopped")

    def pause(self) -> None:
        """Temporarily pause the listener (e.g., during hotkey test)."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._running = False
        logger.debug("Hotkey listener paused")

    def resume(self) -> None:
        """Resume the listener after a pause."""
        if not self._running:
            self.start()

    def update(
        self, new_combo: str | None = None, new_mode: str | None = None
    ) -> None:
        """Update hotkey combo and/or mode in a single restart."""
        was_running = self._running
        self.stop()
        if new_combo is not None:
            self._hotkey_combo = new_combo
            self._hotkey_keys = _parse_hotkey_keys(new_combo)
        if new_mode is not None and new_mode in ("toggle", "hold"):
            self._mode = new_mode
        if was_running:
            self.start()

    def update_hotkey(self, new_combo: str) -> None:
        """Change the hotkey combination. Restarts the listener."""
        self.update(new_combo=new_combo)

    # ------------------------------------------------------------------ #
    # Key event handlers (shared by Quartz and pynput backends)
    # ------------------------------------------------------------------ #

    def _handle_press(self, key_id: str) -> None:
        """Handle key press with normalized key_id string."""
        if not key_id:
            return
        self._pressed_keys.add(key_id)

        if self._hotkey_keys.issubset(self._pressed_keys):
            if self._mode == "toggle":
                if not self._toggle_pressed:
                    self._toggle_pressed = True
                    logger.debug(
                        "Hotkey triggered (toggle): %s", self.hotkey_display
                    )
                    if self._on_toggle:
                        threading.Thread(
                            target=self._on_toggle, daemon=True
                        ).start()
            elif self._mode == "hold":
                if not self._holding:
                    self._holding = True
                    self._hold_start_time = time.monotonic()
                    logger.debug("Hold started: %s", self.hotkey_display)
                    if self._on_hold_start:
                        threading.Thread(
                            target=self._on_hold_start, daemon=True
                        ).start()

    def _handle_release(self, key_id: str) -> None:
        """Handle key release with normalized key_id string."""
        if not key_id:
            return
        self._pressed_keys.discard(key_id)

        if key_id in self._hotkey_keys:
            if self._mode == "toggle":
                self._toggle_pressed = False
            elif self._mode == "hold" and self._holding:
                held_duration = time.monotonic() - self._hold_start_time
                self._holding = False
                if held_duration >= _MIN_HOLD_DURATION:
                    logger.debug(
                        "Hold released after %.1fs: %s",
                        held_duration,
                        self.hotkey_display,
                    )
                    if self._on_hold_stop:
                        threading.Thread(
                            target=self._on_hold_stop, daemon=True
                        ).start()
                else:
                    logger.debug(
                        "Hold too short (%.2fs), ignored", held_duration
                    )

    # ------------------------------------------------------------------ #
    # pynput adapters (non-macOS only)
    # ------------------------------------------------------------------ #

    def _on_pynput_press(self, key) -> None:
        """Convert pynput key to key_id and delegate."""
        self._handle_press(_pynput_key_to_id(key))

    def _on_pynput_release(self, key) -> None:
        """Convert pynput key to key_id and delegate."""
        self._handle_release(_pynput_key_to_id(key))

    @staticmethod
    def default_hotkey() -> str:
        """Return the platform-appropriate default hotkey."""
        if platform.system() == "Darwin":
            return "<cmd>+<shift>+<space>"
        return "<ctrl>+<shift>+<space>"
