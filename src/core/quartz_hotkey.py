"""macOS hotkey listener using Quartz CGEventTap on the main CFRunLoop.

Replaces pynput.keyboard.Listener on macOS to avoid SIGTRAP crashes
caused by pynput calling HIToolbox TSMGetInputSourceProperty from a
background thread (dispatch_assert_queue_fail).

The CGEventTap is added to Qt's main run loop so callbacks fire on the
main thread, which is safe for all macOS APIs.
"""

import logging

from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFMachPortInvalidate,
    CFRunLoopAddSource,
    CFRunLoopGetMain,
    CFRunLoopRemoveSource,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopCommonModes,
    kCGEventFlagsChanged,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)

logger = logging.getLogger(__name__)

# CGEventTapOptions: listen-only (passive), does not block or modify events
_LISTEN_ONLY = 0x00000001

# System sends this event type when the tap is disabled due to slow processing
_TAP_DISABLED_BY_TIMEOUT = 0xFFFFFFFE

# ------------------------------------------------------------------ #
# macOS virtual-keycode tables
# ------------------------------------------------------------------ #

# Named keys -> pynput-compatible key ID format: "<name>"
_KEYCODE_TO_NAME: dict[int, str] = {
    49: "space",
    36: "enter",
    76: "enter",  # numpad enter
    53: "esc",
    51: "backspace",
    48: "tab",
    # Function keys
    122: "f1",
    120: "f2",
    99: "f3",
    118: "f4",
    96: "f5",
    97: "f6",
    98: "f7",
    100: "f8",
    101: "f9",
    109: "f10",
    103: "f11",
    111: "f12",
    105: "f13",
    107: "f14",
    113: "f15",
    # Navigation
    123: "left",
    124: "right",
    125: "down",
    126: "up",
    115: "home",
    119: "end",
    116: "page_up",
    121: "page_down",
    117: "delete",
}

# Regular character keycodes (US keyboard layout)
_KEYCODE_TO_CHAR: dict[int, str] = {
    0: "a",
    1: "s",
    2: "d",
    3: "f",
    4: "h",
    5: "g",
    6: "z",
    7: "x",
    8: "c",
    9: "v",
    11: "b",
    12: "q",
    13: "w",
    14: "e",
    15: "r",
    16: "y",
    17: "t",
    18: "1",
    19: "2",
    20: "3",
    21: "4",
    22: "6",
    23: "5",
    24: "=",
    25: "9",
    26: "7",
    27: "-",
    28: "8",
    29: "0",
    30: "]",
    31: "o",
    32: "u",
    33: "[",
    34: "i",
    35: "p",
    37: "l",
    38: "j",
    40: "k",
    41: ";",
    43: ",",
    44: "/",
    45: "n",
    46: "m",
    47: ".",
    50: "`",
}

# Modifier keycodes -> normalized modifier name
_MODIFIER_KEYCODES: dict[int, str] = {
    56: "shift",
    60: "shift",  # right shift
    59: "ctrl",
    62: "ctrl",  # right control
    58: "alt",
    61: "alt",  # right option
    55: "cmd",
    54: "cmd",  # right command
}

# Modifier name -> CGEvent flag bit
_MODIFIER_FLAG: dict[str, int] = {
    "shift": kCGEventFlagMaskShift,
    "ctrl": kCGEventFlagMaskControl,
    "alt": kCGEventFlagMaskAlternate,
    "cmd": kCGEventFlagMaskCommand,
}


def _keycode_to_id(keycode: int) -> str:
    """Convert a macOS virtual keycode to a pynput-compatible key ID.

    Named keys return ``"<name>"`` (e.g. ``"<f9>"``);
    character keys return the character (e.g. ``"a"``).
    """
    name = _KEYCODE_TO_NAME.get(keycode)
    if name:
        return f"<{name}>"
    char = _KEYCODE_TO_CHAR.get(keycode)
    return char or ""


class QuartzHotkeyListener:
    """Global key-event listener using a Quartz CGEventTap.

    The tap is added to the **main** CFRunLoop (shared with Qt) so
    callbacks always execute on the main thread.

    Args:
        on_press:  Called with key_id string on key-down.
        on_release: Called with key_id string on key-up.
    """

    def __init__(self, on_press=None, on_release=None):
        self._on_press = on_press
        self._on_release = on_release
        self._tap = None
        self._source = None
        self._prev_flags: int = 0
        # prevent GC of callback closure
        self._callback_ref = None

    @property
    def running(self) -> bool:
        return self._tap is not None

    def start(self) -> None:
        """Create and enable the event tap on the main run loop."""
        if self._tap is not None:
            return

        mask = (
            (1 << kCGEventKeyDown)
            | (1 << kCGEventKeyUp)
            | (1 << kCGEventFlagsChanged)
        )

        # Use a closure so the C callback reference stays alive
        def _tap_callback(proxy, event_type, event, refcon):
            return self._on_tap_event(proxy, event_type, event, refcon)

        self._callback_ref = _tap_callback

        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            _LISTEN_ONLY,
            mask,
            self._callback_ref,
            None,
        )

        if self._tap is None:
            raise RuntimeError(
                "Failed to create CGEventTap. "
                "Grant Input Monitoring permission in "
                "System Settings > Privacy & Security > Input Monitoring"
            )

        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(
            CFRunLoopGetMain(), self._source, kCFRunLoopCommonModes
        )
        CGEventTapEnable(self._tap, True)
        self._prev_flags = 0
        logger.info("Quartz CGEventTap started on main run loop")

    def stop(self) -> None:
        """Disable and remove the event tap."""
        if self._tap is None:
            return
        CGEventTapEnable(self._tap, False)
        if self._source is not None:
            CFRunLoopRemoveSource(
                CFRunLoopGetMain(), self._source, kCFRunLoopCommonModes
            )
            self._source = None
        CFMachPortInvalidate(self._tap)
        self._tap = None
        self._callback_ref = None
        logger.info("Quartz CGEventTap stopped")

    # ------------------------------------------------------------------ #
    # Tap callback (runs on main thread via CFRunLoop)
    # ------------------------------------------------------------------ #

    def _on_tap_event(self, proxy, event_type, event, refcon):
        """Process a single CGEvent from the tap."""
        try:
            if event_type == kCGEventKeyDown:
                kid = _keycode_to_id(
                    CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                )
                if kid and self._on_press:
                    self._on_press(kid)

            elif event_type == kCGEventKeyUp:
                kid = _keycode_to_id(
                    CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                )
                if kid and self._on_release:
                    self._on_release(kid)

            elif event_type == kCGEventFlagsChanged:
                self._on_flags_changed(event)

            elif event_type == _TAP_DISABLED_BY_TIMEOUT:
                logger.warning("CGEventTap disabled by timeout; re-enabling")
                if self._tap is not None:
                    CGEventTapEnable(self._tap, True)

        except Exception:
            logger.exception("Error in Quartz hotkey callback")

        return event

    def _on_flags_changed(self, event) -> None:
        """Detect modifier press/release from a flags-changed event."""
        flags = CGEventGetFlags(event)
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        mod_name = _MODIFIER_KEYCODES.get(keycode)
        if not mod_name:
            self._prev_flags = flags
            return

        flag_bit = _MODIFIER_FLAG.get(mod_name, 0)
        if not flag_bit:
            self._prev_flags = flags
            return

        key_id = f"<{mod_name}>"
        now_pressed = bool(flags & flag_bit)
        was_pressed = bool(self._prev_flags & flag_bit)
        self._prev_flags = flags

        if now_pressed and not was_pressed:
            if self._on_press:
                self._on_press(key_id)
        elif not now_pressed and was_pressed:
            if self._on_release:
                self._on_release(key_id)
