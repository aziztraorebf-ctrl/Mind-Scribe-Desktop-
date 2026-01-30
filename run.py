"""MindScribe Desktop - Simple launcher script."""

import logging
import signal
import sys
import time

# Configure logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src.app import MindScribeApp


def main():
    app = MindScribeApp()

    def on_state_change(state):
        print(f"  [{state.name}]")

    def on_transcription_done(text):
        print(f"  Transcribed ({len(text)} chars): {text[:200]}{'...' if len(text) > 200 else ''}")

    def on_error(msg):
        print(f"  ERROR: {msg}", file=sys.stderr)

    # Event to signal shutdown (from tray Quit or Ctrl+C)
    import threading
    shutdown_event = threading.Event()

    def on_quit_request():
        print("\nQuit requested from tray menu.")
        shutdown_event.set()

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

    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down...")
        app.stop()


if __name__ == "__main__":
    main()
