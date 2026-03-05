"""MindScribe Desktop - Main application orchestration."""

import logging
import platform
import threading
import time
from enum import Enum, auto

_IS_MACOS = platform.system() == "Darwin"

from src.config.dotenv_loader import load_env
from src.config.settings import Settings
from src.core.audio_recorder import AudioRecorder
from src.core.chunker import prepare_audio
from src.core.hotkey_manager import HotkeyManager
from src.core.text_inserter import insert_text
from src.core.transcriber import Transcriber, TranscriptionError
from src.core.history_store import HistoryStore
from src.core.style_store import StyleStore
from src.ui.dashboard import Dashboard
from src.ui.notification import notify
from src.ui.overlay import RecordingOverlay
from src.ui.sounds import play_ready, play_record_start, play_record_stop
from src.ui.settings_window import SettingsWindow
from src.ui.tray_icon import TrayIcon
from src.core.vocabulary_store import VocabularyStore
from src.core.vad_filter import filter_silence

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
        self.vocabulary = VocabularyStore()
        env_keys = load_env()
        self.settings.merge_env(
            groq_key=env_keys["groq_api_key"],
            openai_key=env_keys["openai_api_key"],
        )

        # State
        self._state = AppState.IDLE
        self._lock = threading.Lock()
        self._previous_app = None  # NSRunningApplication saved before recording

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
            prompt=self._effective_prompt(),
        )
        self.hotkey_manager = HotkeyManager(
            on_toggle=self._on_hotkey_toggle,
            on_hold_start=self._on_hold_start,
            on_hold_stop=self._on_hold_stop,
            hotkey_combo=self.settings.hotkey,
            mode=self.settings.record_mode,
        )

        # Data stores
        self.history_store = HistoryStore()
        self.style_store = StyleStore()

        # Dashboard window
        self.dashboard = Dashboard(
            history_store=self.history_store,
            style_store=self.style_store,
            vocabulary=self.vocabulary,
            settings=self.settings,
            on_style_change=self._on_style_change,
            on_settings_save=self._on_settings_saved,
        )

        # System tray
        self.tray = TrayIcon(
            on_toggle=self._on_hotkey_toggle,
            on_settings=self._open_settings,
            on_dashboard=self._open_dashboard,
            on_quit=self._request_quit,
            hotkey_display=self.hotkey_manager.hotkey_display,
        )

        # Floating overlay (QWidget — must be created before settings window)
        self.overlay = RecordingOverlay()

        # Settings window (QWidget — independent top-level window)
        self.settings_window = SettingsWindow(
            settings=self.settings,
            on_save=self._on_settings_saved,
            vocabulary=self.vocabulary,
        )
        self.settings_window.set_hotkey_manager(self.hotkey_manager)
        self.dashboard.set_hotkey_manager(self.hotkey_manager)

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

    def _capture_previous_app(self) -> None:
        """Snapshot the current frontmost non-MindScribe app.

        Called from hotkey callbacks BEFORE any UI change (overlay show, etc.)
        so we always capture the real user app, not our own window.

        When running as a plain Python script (not a packaged .app), NSWorkspace
        reports the process as "python" with no bundle ID.  We filter by PID
        comparison instead of by name/bundle in that case.
        """
        if not _IS_MACOS:
            return
        try:
            import os
            from AppKit import NSWorkspace
            candidate = NSWorkspace.sharedWorkspace().frontmostApplication()
            if candidate is None:
                return
            # Filter out our own process (works whether packaged or run as python)
            if candidate.processIdentifier() == os.getpid():
                logger.debug(
                    "frontmost app is our own process (pid=%d), keeping previous: %s",
                    os.getpid(),
                    self._previous_app.localizedName() if self._previous_app else "None",
                )
                return
            name = candidate.localizedName() or ""
            bundle = candidate.bundleIdentifier() or ""
            # Belt-and-suspenders: also filter by name/bundle for packaged .app
            if "MindScribe" in name or bundle.startswith("com.mindscribe"):
                logger.debug(
                    "frontmost app is MindScribe (%s), keeping previous: %s",
                    name,
                    self._previous_app.localizedName() if self._previous_app else "None",
                )
                return
            self._previous_app = candidate
            logger.info("Captured previous app: %s (pid=%d)", name, candidate.processIdentifier())
        except Exception as exc:
            logger.warning("Could not capture previous app: %s", exc)

    def _effective_prompt(self) -> str:
        return self.settings.prompt + self.vocabulary.build_prompt_suffix()

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

        # Show brief "Ready" overlay so the user knows the app is running
        self.overlay.show_ready(self.hotkey_manager.hotkey_display)
        play_ready()

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

    def _open_dashboard(self) -> None:
        """Open the dashboard window."""
        self.dashboard.open()

    def _on_style_change(self, style_name: str, prompt: str) -> None:
        """Handle style change from the dashboard."""
        self.settings.active_style = style_name
        self.settings.save()
        if prompt:
            self.transcriber.prompt = prompt + " " + self._effective_prompt()
        else:
            self.transcriber.prompt = self._effective_prompt()
        self.tray.update_style_display(style_name)
        logger.info("Active style changed to: %s", style_name)

    def _on_settings_saved(self, settings: Settings) -> None:
        """Apply updated settings to live components."""
        logger.info("Settings updated. Applying changes...")

        # Update transcriber with new settings
        self.transcriber.language = settings.language
        self.transcriber.model = settings.whisper_model
        self.transcriber.prompt = self._effective_prompt()
        self.transcriber.primary_provider = settings.primary_provider

        # Update recorder device (takes effect on next recording)
        self.recorder.device = settings.input_device

        # Update hotkey manager (single restart, avoids double stop/start)
        self.hotkey_manager.update(
            new_combo=settings.hotkey,
            new_mode=settings.record_mode,
        )

        # Update tray icon menu text with new hotkey
        self.tray.update_hotkey_display(self.hotkey_manager.hotkey_display)

        logger.info(
            "Applied: language=%s, model=%s, provider=%s, mode=%s, hotkey=%s",
            settings.language,
            settings.whisper_model,
            settings.primary_provider,
            settings.record_mode,
            self.hotkey_manager.hotkey_display,
        )

    def _on_hotkey_toggle(self) -> None:
        """Handle hotkey press - toggle between recording and idle."""
        with self._lock:
            if self._state == AppState.IDLE:
                self._capture_previous_app()
                self._start_recording()
            elif self._state in (AppState.RECORDING, AppState.PAUSED):
                self._stop_and_transcribe()
            # If TRANSCRIBING, ignore the hotkey (still processing)

    def _on_hold_start(self) -> None:
        """Handle hotkey hold start - begin recording."""
        with self._lock:
            if self._state == AppState.IDLE:
                self._capture_previous_app()
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
        if self._previous_app:
            logger.info("Recording will return to: %s", self._previous_app.localizedName())
        else:
            logger.warning("No previous app captured — text may not be inserted correctly.")
        # Hide dashboard so the user's target app (e.g. VS Code) appears in the
        # background behind the overlay, not the Dashboard.
        self.dashboard.hide_if_open()
        self._set_state(AppState.RECORDING)
        self.tray.set_recording()
        self.overlay.show_recording()
        self.recorder.start()
        play_record_start()
        logger.info("Recording started...")

    def _stop_and_transcribe(self, from_overlay: bool = False) -> None:
        """Stop recording and transcribe in a background thread.

        Args:
            from_overlay: If True, hide overlay immediately so the OS returns
                          focus to the previous window before pasting.
        """
        self._set_state(AppState.TRANSCRIBING)
        self.tray.set_transcribing()
        play_record_stop()

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
            if self.settings.show_notifications:
                notify("MindScribe", "No audio captured. Try speaking louder or check your microphone.")
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
            # Strip silence before sending to API
            wav_data = filter_silence(wav_data)
            if not wav_data:
                logger.info("VAD: no speech detected, skipping transcription")
                self.overlay.hide()
                self.tray.set_idle()
                self._set_state(AppState.IDLE)
                if self.settings.show_notifications:
                    notify("MindScribe", "No speech detected.")
                return

            # Prepare audio (compress/chunk if needed)
            audio_chunks = prepare_audio(wav_data)

            if not audio_chunks:
                logger.warning("No audio data after preparation.")
                if self.settings.show_notifications:
                    notify("MindScribe", "Recording too short or empty.")
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

            # Hide overlay BEFORE pasting so the OS returns focus to the
            # user's target window.  Without this, Cmd+V lands in the
            # overlay (which has no text fields) and the text is lost.
            self.overlay.hide()
            self.tray.set_idle()

            # Reactivate the previous app using osascript (synchronous, reliable).
            # activateWithOptions_ from a background thread is non-deterministic.
            if _IS_MACOS and self._previous_app is not None:
                try:
                    import os
                    import subprocess
                    # Safety: never activate our own process (happens when running
                    # as plain python script — NSWorkspace reports us as "python"
                    # with no bundle ID, which would land the paste in MindScribe).
                    if self._previous_app.processIdentifier() == os.getpid():
                        logger.warning(
                            "previous_app points to our own process — skipping activation"
                        )
                    else:
                        bundle_id = self._previous_app.bundleIdentifier() or ""
                        app_name = self._previous_app.localizedName() or ""
                        if bundle_id:
                            script = f'tell application id "{bundle_id}" to activate'
                        elif app_name:
                            safe_name = app_name.replace('"', '\\"')
                            script = f'tell application "{safe_name}" to activate'
                        else:
                            script = None
                        if script:
                            subprocess.run(
                                ["osascript", "-e", script],
                                capture_output=True,
                                timeout=3,
                            )
                            logger.debug(
                                "Reactivated previous app via osascript: %s",
                                app_name or bundle_id,
                            )
                except Exception as exc:
                    logger.warning("Failed to reactivate previous app: %s", exc)

            # Wait for macOS to complete the app switch before pasting.
            time.sleep(0.8)

            insert_text(
                full_text,
                restore_clipboard=self.settings.restore_clipboard,
                restore_delay=self.settings.clipboard_restore_delay,
            )

            # Store in history
            self.history_store.add(full_text, duration_seconds=self.recorder.duration_seconds)

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
            self.overlay.hide()
            self.tray.set_idle()
            self._set_state(AppState.IDLE)

    def _set_state(self, new_state: AppState) -> None:
        """Update application state and notify listeners."""
        self._state = new_state
        logger.debug("State changed to: %s", new_state.name)
        if self.on_state_change:
            self.on_state_change(new_state)
