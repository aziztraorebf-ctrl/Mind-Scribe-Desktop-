"""Insert transcribed text into the active application field."""

import logging
import platform
import time
import threading

import pyperclip
from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)

_keyboard = Controller()


def insert_text(
    text: str,
    restore_clipboard: bool = True,
    restore_delay: float = 0.5,
) -> None:
    """Insert text into the currently active field via clipboard paste.

    Strategy:
    1. Save current clipboard content
    2. Copy transcribed text to clipboard
    3. Simulate Ctrl+V (Windows/Linux) or Cmd+V (macOS) to paste
    4. Wait briefly, then restore original clipboard content
    """
    if not text:
        return

    # Save current clipboard
    original_clipboard = ""
    if restore_clipboard:
        try:
            original_clipboard = pyperclip.paste()
        except Exception:
            original_clipboard = ""

    # Copy transcription to clipboard
    pyperclip.copy(text)

    # Small delay to ensure clipboard is updated
    time.sleep(0.05)

    # Simulate paste
    _paste()

    # Restore clipboard in background
    if restore_clipboard and original_clipboard:
        def _restore():
            time.sleep(restore_delay)
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass

        threading.Thread(target=_restore, daemon=True).start()

    logger.info("Inserted %d characters into active field", len(text))


def _paste() -> None:
    """Simulate a paste keyboard shortcut."""
    system = platform.system()

    if system == "Darwin":
        # macOS: Cmd+V
        _keyboard.press(Key.cmd)
        _keyboard.press("v")
        _keyboard.release("v")
        _keyboard.release(Key.cmd)
    else:
        # Windows/Linux: Ctrl+V
        _keyboard.press(Key.ctrl)
        _keyboard.press("v")
        _keyboard.release("v")
        _keyboard.release(Key.ctrl)
