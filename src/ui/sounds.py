"""App sound effects using macOS system sounds (NSSound).

On non-macOS platforms, sounds are silently skipped.
All play functions are non-blocking and safe to call from any thread.
"""

import logging
import platform

logger = logging.getLogger(__name__)

_IS_MACOS = platform.system() == "Darwin"

# macOS system sound names (from /System/Library/Sounds/)
_SOUND_READY = "Glass"
_SOUND_RECORD_START = "Tink"
_SOUND_RECORD_STOP = "Pop"


def _play(name: str) -> None:
    """Play a macOS system sound by name (non-blocking)."""
    if not _IS_MACOS:
        return
    try:
        from AppKit import NSSound

        sound = NSSound.soundNamed_(name)
        if sound:
            sound.play()
    except Exception:
        logger.debug("Could not play sound: %s", name)


def play_ready() -> None:
    """App startup / ready sound."""
    _play(_SOUND_READY)


def play_record_start() -> None:
    """Recording started sound."""
    _play(_SOUND_RECORD_START)


def play_record_stop() -> None:
    """Recording stopped sound."""
    _play(_SOUND_RECORD_STOP)
