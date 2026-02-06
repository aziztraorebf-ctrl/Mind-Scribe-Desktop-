"""MindScribe Desktop - Simple launcher script.

PyQt6 version: QApplication event loop runs on the main thread (required by
macOS Cocoa). Hotkeys and tray icon run in their own daemon threads.
"""

import logging
import signal
import sys

# Configure logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def main():
    # Run macOS preflight checks before anything else
    import platform
    if platform.system() == "Darwin":
        try:
            from src.preflight_macos import run_preflight_checks
            warnings = run_preflight_checks()
            for w in warnings:
                print(f"  WARNING: {w}", file=sys.stderr)
        except ImportError:
            pass

    from PyQt6.QtWidgets import QApplication
    from src.app import MindScribeApp

    # QApplication must be created on the main thread (macOS requirement)
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # Keep running as tray app
    qt_app.setApplicationName("MindScribe Desktop")

    app = MindScribeApp()

    def on_state_change(state):
        print(f"  [{state.name}]")

    def on_transcription_done(text):
        print(f"  Transcribed ({len(text)} chars): {text[:200]}{'...' if len(text) > 200 else ''}")

    def on_error(msg):
        print(f"  ERROR: {msg}", file=sys.stderr)

    def on_quit_request():
        print("\nQuit requested from tray menu.")
        qt_app.quit()

    app.on_state_change = on_state_change
    app.on_transcription_done = on_transcription_done
    app.on_error = on_error
    app.on_quit_request = on_quit_request

    print("=" * 55)
    print("  MindScribe Desktop")
    print("=" * 55)
    print(f"  Hotkey     : {app.hotkey_manager.hotkey_display}")
    print(f"  Language   : {app.settings.language}")
    print(f"  Provider   : {app.settings.primary_provider}")
    print(f"  Model      : {app.settings.whisper_model}")
    print(f"  Mode       : {app.settings.record_mode}")
    print("=" * 55)
    print("  Press the hotkey to START recording.")
    print("  Press it again to STOP and transcribe.")
    print("  Text will be pasted into the active field.")
    print("  Right-click the tray icon or press Ctrl+C to quit.")
    print("=" * 55)

    app.start()

    # Handle Ctrl+C: schedule Qt quit from the signal handler
    def sigint_handler(sig, frame):
        print("\nShutting down...")
        app.stop()
        qt_app.quit()

    signal.signal(signal.SIGINT, sigint_handler)

    # Allow Python signal handlers to fire during Qt event loop
    # (Qt blocks Python signals otherwise)
    from PyQt6.QtCore import QTimer
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # triggers Python signal check

    # Enter the Qt event loop (main thread stays here)
    exit_code = qt_app.exec()

    app.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
