"""MindScribe Desktop - Main application orchestration."""

import logging
import threading
import time
from enum import Enum, auto

from src.config.dotenv_loader import load_env
from src.config.settings import Settings
from src.core.audio_recorder import AudioRecorder
from src.core.chunker import prepare_audio
from src.core.hotkey_manager import HotkeyManager
from src.core.text_inserter import insert_text
from src.core.transcriber import Transcriber, TranscriptionError
from src.ui.notification import notify
from src.ui.overlay import RecordingOverlay
from src.ui.settings_window import SettingsWindow
from src.ui.tray_icon import TrayIcon

logger = logging.getLogger(__name__)


class AppState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()
    TRANSCRIBING = auto()


class MindScribeApp:
    """Main application that orchestrates recording, transcription, and text insertion."""

    def __init__(self) -> None:
        # Load configuration
        self.settings = Settings.load()
        env_keys = load_env()
        self.settings.merge_env(
            groq_key=env_keys["groq_api_key"],
            openai_key=env_keys["openai_api_key"],
        )

        # State
        self._state = AppState.IDLE
        self._lock = threading.Lock()

        # Components
        self.recorder = AudioRecorder(
            sample_rate=self.settings.sample_rate,
            channels=self.settings.channels,
            device=self.settings.input_device,
        )
        self.transcriber = Transcriber(
            groq_api_key=self.settings.groq_api_key,
            openai_api_key=self.settings.openai_api_key,
            primary_provider=self.settings.primary_provider,
            model=self.settings.whisper_model,
            language=self.settings.language,
            prompt=self.settings.prompt,
        )
        self.hotkey_manager = HotkeyManager(
            on_toggle=self._on_hotkey_toggle,
            on_hold_start=self._on_hold_start,
            on_hold_stop=self._on_hold_stop,
            hotkey_combo=self.settings.hotkey,
            mode=self.settings.record_mode,
        )

        # System tray
        self.tray = TrayIcon(
            on_toggle=self._on_hotkey_toggle,
            on_settings=self._open_settings,
            on_quit=self._request_quit,
            hotkey_display=self.hotkey_manager.hotkey_display,
        )

        # Settings window
        self.settings_window = SettingsWindow(
            settings=self.settings,
            on_save=self._on_settings_saved,
        )

        # Floating overlay
        self.overlay = RecordingOverlay()

        # Connect overlay to audio recorder for real-time levels
        self.overlay.set_audio_source(
            get_levels=lambda: self.recorder.level_history,
            get_duration=lambda: self.recorder.duration_seconds,
        )

        # Connect overlay action buttons
        self.overlay.on_stop = self._on_overlay_stop
        self.overlay.on_cancel = self._on_overlay_cancel
        self.overlay.on_pause = self._on_overlay_pause

        # Callbacks for UI updates
        self.on_state_change: callable | None = None
        self.on_transcription_done: callable | None = None
        self.on_error: callable | None = None
        self.on_quit_request: callable | None = None

    @property
    def state(self) -> AppState:
        return self._state

    def start(self) -> None:
        """Start the application (begin listening for hotkeys)."""
        if not self.transcriber.is_configured:
            logger.error("No API keys configured. Set GROQ_API_KEY or OPENAI_API_KEY in .env")
            if self.on_error:
                self.on_error("No API keys configured. Check your .env file.")
            return

        self.hotkey_manager.start()
        self.tray.start()
        self.overlay.start()

        # Share the overlay's tk root with the settings window
        if self.overlay.tk_root is not None:
            self.settings_window.set_tk_root(self.overlay.tk_root)

        logger.info(
            "MindScribe Desktop started. Press %s to toggle recording.",
            self.hotkey_manager.hotkey_display,
        )

    def stop(self) -> None:
        """Stop the application."""
        self.hotkey_manager.stop()
        self.overlay.stop()
        self.tray.stop()
        if self._state in (AppState.RECORDING, AppState.PAUSED):
            self.recorder.cancel()
        self._set_state(AppState.IDLE)
        logger.info("MindScribe Desktop stopped.")

    def _request_quit(self) -> None:
        """Called when user clicks Quit in tray menu."""
        self.stop()
        if self.on_quit_request:
            self.on_quit_request()

    def _open_settings(self) -> None:
        """Open the settings window."""
        self.settings_window.open()

    def _on_settings_saved(self, settings: Settings) -> None:
        """Apply updated settings to live components."""
        logger.info("Settings updated. Applying changes...")

        # Update transcriber with new settings
        self.transcriber.language = settings.language
        self.transcriber.model = settings.whisper_model
        self.transcriber.prompt = settings.prompt
        self.transcriber.primary_provider = settings.primary_provider

        # Update recorder device (takes effect on next recording)
        self.recorder.device = settings.input_device

        # Update hotkey manager mode and hotkey
        self.hotkey_manager.mode = settings.record_mode
        self.hotkey_manager.update_hotkey(settings.hotkey)

        logger.info(
            "Applied: language=%s, model=%s, provider=%s, mode=%s",
            settings.language,
            settings.whisper_model,
            settings.primary_provider,
            settings.record_mode,
        )

    def _on_hotkey_toggle(self) -> None:
        """Handle hotkey press - toggle between recording and idle."""
        with self._lock:
            if self._state == AppState.IDLE:
                self._start_recording()
            elif self._state in (AppState.RECORDING, AppState.PAUSED):
                self._stop_and_transcribe()
            # If TRANSCRIBING, ignore the hotkey (still processing)

    def _on_hold_start(self) -> None:
        """Handle hotkey hold start - begin recording."""
        with self._lock:
            if self._state == AppState.IDLE:
                self._start_recording()

    def _on_hold_stop(self) -> None:
        """Handle hotkey hold release - stop and transcribe."""
        with self._lock:
            if self._state in (AppState.RECORDING, AppState.PAUSED):
                self._stop_and_transcribe()

    def _on_overlay_stop(self) -> None:
        """Handle Stop button from overlay.

        Hides overlay first so Windows returns focus to the previous window
        before the transcribed text is pasted.
        """
        with self._lock:
            if self._state in (AppState.RECORDING, AppState.PAUSED):
                self._stop_and_transcribe(from_overlay=True)

    def _on_overlay_cancel(self) -> None:
        """Handle Cancel button from overlay - discard recording."""
        with self._lock:
            if self._state in (AppState.RECORDING, AppState.PAUSED):
                self.recorder.cancel()
                self.tray.set_idle()
                self.overlay.hide()
                self._set_state(AppState.IDLE)
                logger.info("Recording cancelled by user.")
                if self.settings.show_notifications:
                    notify("MindScribe", "Recording cancelled.")

    def _on_overlay_pause(self) -> None:
        """Handle Pause/Resume button from overlay."""
        with self._lock:
            if self._state == AppState.RECORDING:
                self.recorder.pause()
                self._set_state(AppState.PAUSED)
                self.overlay.show_paused()
                logger.info("Recording paused.")
            elif self._state == AppState.PAUSED:
                self.recorder.resume()
                self._set_state(AppState.RECORDING)
                self.overlay.show_recording()
                logger.info("Recording resumed.")

    def _start_recording(self) -> None:
        """Begin recording audio."""
        self._set_state(AppState.RECORDING)
        self.tray.set_recording()
        self.overlay.show_recording()
        self.recorder.start()
        logger.info("Recording started...")

    def _stop_and_transcribe(self, from_overlay: bool = False) -> None:
        """Stop recording and transcribe in a background thread.

        Args:
            from_overlay: If True, hide overlay immediately so the OS returns
                          focus to the previous window before pasting.
        """
        self._set_state(AppState.TRANSCRIBING)
        self.tray.set_transcribing()

        if from_overlay:
            # Hide overlay so focus returns to the user's target window
            self.overlay.hide()
        else:
            self.overlay.show_transcribing()

        wav_data = self.recorder.stop()

        if not wav_data:
            logger.warning("No audio recorded.")
            self.tray.set_idle()
            self.overlay.hide()
            self._set_state(AppState.IDLE)
            return

        duration = self.recorder.duration_seconds
        logger.info("Recording stopped. Duration: %.1f seconds. Transcribing...", duration)

        # Transcribe in background to avoid blocking the hotkey listener
        threading.Thread(
            target=self._transcribe_and_insert,
            args=(wav_data, from_overlay),
            daemon=True,
        ).start()

    def _transcribe_and_insert(self, wav_data: bytes, from_overlay: bool = False) -> None:
        """Transcribe audio and insert the text into the active field."""
        try:
            if from_overlay:
                # Give Windows time to return focus to the previous window
                time.sleep(0.3)
            # Prepare audio (compress/chunk if needed)
            audio_chunks = prepare_audio(wav_data)

            if not audio_chunks:
                logger.warning("No audio data after preparation.")
                self._set_state(AppState.IDLE)
                return

            # Transcribe each chunk and concatenate
            texts = []
            for i, chunk in enumerate(audio_chunks):
                logger.info("Transcribing chunk %d/%d...", i + 1, len(audio_chunks))
                text = self.transcriber.transcribe(chunk)
                texts.append(text)

            full_text = " ".join(texts)

            # Optional LLM post-processing (clean up formatting)
            if self.settings.post_process and full_text:
                logger.info("Post-processing transcription...")
                full_text = self.transcriber.post_process(full_text)

            # Insert into active field
            insert_text(
                full_text,
                restore_clipboard=self.settings.restore_clipboard,
                restore_delay=self.settings.clipboard_restore_delay,
            )

            logger.info("Transcription complete: %d chars", len(full_text))
            if self.settings.show_notifications:
                preview = full_text[:80] + ("..." if len(full_text) > 80 else "")
                notify("MindScribe", f"Transcribed: {preview}")
            if self.on_transcription_done:
                self.on_transcription_done(full_text)

        except TranscriptionError as exc:
            logger.error("Transcription failed: %s", exc)
            if self.settings.show_notifications:
                notify("MindScribe - Error", str(exc))
            if self.on_error:
                self.on_error(str(exc))

        except Exception as exc:
            logger.error("Unexpected error during transcription: %s", exc)
            if self.settings.show_notifications:
                notify("MindScribe - Error", f"Unexpected error: {exc}")
            if self.on_error:
                self.on_error(f"Unexpected error: {exc}")

        finally:
            self.tray.set_idle()
            self.overlay.hide()
            self._set_state(AppState.IDLE)

    def _set_state(self, new_state: AppState) -> None:
        """Update application state and notify listeners."""
        self._state = new_state
        logger.debug("State changed to: %s", new_state.name)
        if self.on_state_change:
            self.on_state_change(new_state)
