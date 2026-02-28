"""Insert transcribed text into the active application field.

On macOS, uses Quartz CGEventPost for keystroke simulation (more reliable
than pynput Controller and avoids Quartz/AppKit threading issues).
On other platforms, uses pynput keyboard.Controller.
"""

import logging
import platform
import threading
import time

import pyperclip

logger = logging.getLogger(__name__)

_IS_MACOS = platform.system() == "Darwin"

if not _IS_MACOS:
    from pynput.keyboard import Controller, Key

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

    # Delay to ensure clipboard is synced before pasting
    # macOS needs longer due to pasteboard daemon latency
    if _IS_MACOS:
        time.sleep(0.15)
    else:
        time.sleep(0.05)

    # Simulate paste
    _paste()

    # Restore clipboard in background
    if restore_clipboard and original_clipboard:
        # macOS pasteboard needs more time before safe to restore
        actual_delay = (
            max(restore_delay, 1.0) if _IS_MACOS else restore_delay
        )

        def _restore():
            time.sleep(actual_delay)
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass

        threading.Thread(target=_restore, daemon=True).start()

    logger.info("Inserted %d characters into active field", len(text))


def _paste() -> None:
    """Simulate a paste keyboard shortcut."""
    if _IS_MACOS:
        _paste_macos()
    else:
        # Windows/Linux: Ctrl+V
        _keyboard.press(Key.ctrl)
        _keyboard.press("v")
        _keyboard.release("v")
        _keyboard.release(Key.ctrl)


def _paste_macos() -> None:
    """Paste on macOS using Quartz CGEventPost (Cmd+V)."""
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPost,
            CGEventSetFlags,
            kCGEventFlagMaskCommand,
            kCGHIDEventTap,
        )

        # 'v' key = macOS virtual keycode 9
        v_down = CGEventCreateKeyboardEvent(None, 9, True)
        CGEventSetFlags(v_down, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, v_down)

        time.sleep(0.05)

        v_up = CGEventCreateKeyboardEvent(None, 9, False)
        CGEventSetFlags(v_up, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, v_up)

    except Exception:
        logger.warning("Quartz CGEventPost paste failed, trying osascript")
        _paste_macos_osascript()


def _paste_macos_osascript() -> None:
    """Fallback paste on macOS using osascript."""
    import subprocess

    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        logger.error(
            "osascript paste also failed: %s. "
            "Text is available in clipboard (Cmd+V to paste manually).",
            exc,
        )
