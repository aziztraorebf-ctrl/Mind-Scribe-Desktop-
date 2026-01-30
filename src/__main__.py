"""MindScribe Desktop - Entry point."""

import logging
import signal
import sys

from src.app import MindScribeApp


def main() -> None:
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = MindScribeApp()

    # Callback handlers for console output
    def on_state_change(state):
        print(f"  [{state.name}]")

    def on_transcription_done(text):
        print(f"  Transcribed: {text[:100]}{'...' if len(text) > 100 else ''}")

    def on_error(msg):
        print(f"  ERROR: {msg}", file=sys.stderr)

    app.on_state_change = on_state_change
    app.on_transcription_done = on_transcription_done
    app.on_error = on_error

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nShutting down...")
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Start
    print("=" * 50)
    print("  MindScribe Desktop")
    print("=" * 50)
    print(f"  Hotkey: {app.hotkey_manager.hotkey_display}")
    print(f"  Language: {app.settings.language}")
    print(f"  Provider: {app.settings.primary_provider}")
    print(f"  Model: {app.settings.whisper_model}")
    print(f"  Mode: {app.settings.record_mode}")
    print("=" * 50)
    print("  Press the hotkey to start/stop recording.")
    print("  Press Ctrl+C to quit.")
    print("=" * 50)

    app.start()

    # Keep the main thread alive
    signal.pause() if hasattr(signal, "pause") else _windows_wait()


def _windows_wait() -> None:
    """Windows doesn't have signal.pause(), so we use a blocking loop."""
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
