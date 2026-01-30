"""System notifications for transcription events."""

import logging
import platform
import threading

logger = logging.getLogger(__name__)


def notify(title: str, message: str) -> None:
    """Show a native system notification (non-blocking)."""
    threading.Thread(
        target=_send_notification,
        args=(title, message),
        daemon=True,
    ).start()


def _send_notification(title: str, message: str) -> None:
    """Send notification using platform-appropriate method."""
    system = platform.system()
    try:
        if system == "Windows":
            _notify_windows(title, message)
        elif system == "Darwin":
            _notify_macos(title, message)
        else:
            _notify_plyer(title, message)
    except Exception as exc:
        logger.debug("Notification failed: %s", exc)


def _notify_windows(title: str, message: str) -> None:
    """Windows 10/11 toast notification via plyer."""
    from plyer import notification as plyer_notif
    plyer_notif.notify(
        title=title,
        message=message,
        app_name="MindScribe Desktop",
        timeout=3,
    )


def _notify_macos(title: str, message: str) -> None:
    """macOS notification via osascript."""
    import subprocess
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)


def _notify_plyer(title: str, message: str) -> None:
    """Fallback using plyer (Linux/other)."""
    from plyer import notification as plyer_notif
    plyer_notif.notify(
        title=title,
        message=message,
        app_name="MindScribe Desktop",
        timeout=3,
    )
