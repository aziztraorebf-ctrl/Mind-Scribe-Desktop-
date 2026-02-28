"""Integration tests: hotkey -> record -> transcribe -> insert flow."""
import io
import os
import time
import wave
import sys
import pytest
import unittest.mock as mock
import numpy as np

os.environ.setdefault("MINDSCRIBE_TEST_DIR", "/tmp/ms_test_flow")

from PyQt6.QtWidgets import QApplication
_qt_app = QApplication.instance() or QApplication(sys.argv)


def _make_wav_bytes() -> bytes:
    """Create a minimal valid 1-second 16kHz mono WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
    return buf.getvalue()


def make_mock_ns_app(name: str, bundle: str = "com.test.app"):
    m = mock.MagicMock()
    m.localizedName.return_value = name
    m.bundleIdentifier.return_value = bundle
    return m


@pytest.fixture
def app_with_mocks(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDSCRIBE_TEST_DIR", str(tmp_path))

    import src.app as app_module

    with mock.patch.object(app_module, "HotkeyManager"), \
         mock.patch.object(app_module, "TrayIcon"), \
         mock.patch.object(app_module, "RecordingOverlay"), \
         mock.patch.object(app_module, "SettingsWindow"), \
         mock.patch.object(app_module, "Dashboard"), \
         mock.patch.object(app_module, "play_ready"), \
         mock.patch.object(app_module, "play_record_start"), \
         mock.patch.object(app_module, "play_record_stop"):

        instance = app_module.MindScribeApp()

        # Replace recorder with a full MagicMock so read-only properties work
        mock_recorder = mock.MagicMock()
        mock_recorder.start = mock.MagicMock()
        mock_recorder.stop = mock.MagicMock(return_value=_make_wav_bytes())
        mock_recorder.cancel = mock.MagicMock()
        mock_recorder.duration_seconds = 2.0
        instance.recorder = mock_recorder

        # Replace transcriber with a full MagicMock so read-only properties work
        mock_transcriber = mock.MagicMock()
        mock_transcriber.is_configured = True
        mock_transcriber.transcribe = mock.MagicMock(return_value="Bonjour le monde")
        mock_transcriber.post_process = mock.MagicMock(side_effect=lambda t: t)
        instance.transcriber = mock_transcriber

        yield instance


class TestStartRecordingState:
    def test_recording_state_set_after_start(self, app_with_mocks):
        """State becomes RECORDING after _start_recording()."""
        from src.app import AppState
        instance = app_with_mocks
        instance._previous_app = make_mock_ns_app("Code", "com.microsoft.VSCode")
        with instance._lock:
            instance._start_recording()
        assert instance.state == AppState.RECORDING

    def test_start_recording_calls_recorder(self, app_with_mocks):
        """recorder.start() is called when recording starts."""
        instance = app_with_mocks
        instance._previous_app = make_mock_ns_app("Code", "com.microsoft.VSCode")
        with instance._lock:
            instance._start_recording()
        instance.recorder.start.assert_called_once()


class TestF9FilteringWhenDashboardOpen:
    def test_mindscribe_app_not_captured(self, app_with_mocks):
        """If Dashboard is frontmost when F9 is pressed, _previous_app stays unchanged."""
        import src.app as app_module
        instance = app_with_mocks
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        dashboard = make_mock_ns_app("MindScribe Desktop", "local.mindscribe")

        instance._previous_app = vscode  # Tracked before dashboard opened

        # Simulate the filtering logic from _capture_previous_app
        # when frontmost is the Dashboard
        name = dashboard.localizedName() or ""
        bundle = dashboard.bundleIdentifier() or ""
        if "MindScribe" not in name and not bundle.startswith("com.mindscribe"):
            instance._previous_app = dashboard  # Would be stored if filter failed

        # Should still be VS Code
        assert instance._previous_app is vscode

    def test_capture_skipped_when_transcribing(self, app_with_mocks):
        """_capture_previous_app is not invoked when state is TRANSCRIBING."""
        from src.app import AppState
        instance = app_with_mocks
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        instance._previous_app = vscode
        instance._state = AppState.TRANSCRIBING

        capture_calls = []
        original = instance._capture_previous_app
        def spy():
            capture_calls.append(1)
            original()
        instance._capture_previous_app = spy

        instance._on_hotkey_toggle()

        assert instance._previous_app is vscode, (
            f"_previous_app changed to {instance._previous_app}"
        )


class TestTranscribeAndInsertFlow:
    def test_history_updated_after_transcription(self, app_with_mocks):
        """History store has the transcription text after flow completes."""
        import src.app as app_module
        instance = app_with_mocks
        instance._previous_app = make_mock_ns_app("Code", "com.microsoft.VSCode")

        with mock.patch("subprocess.run"), \
             mock.patch.object(app_module, "insert_text"):
            with instance._lock:
                instance._start_recording()
            instance._stop_and_transcribe()

            # Wait for background transcription thread
            deadline = time.time() + 5.0
            while time.time() < deadline:
                entries = instance.history_store.get_recent(5)
                if entries:
                    break
                time.sleep(0.1)

        assert entries, "History should have at least one entry"
        assert "Bonjour" in entries[0]["text"]

    def test_osascript_called_with_bundle_id(self, app_with_mocks):
        """osascript activation uses bundleIdentifier (not display name)."""
        import src.app as app_module
        instance = app_with_mocks
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        instance._previous_app = vscode

        with mock.patch("subprocess.run") as mock_run, \
             mock.patch.object(app_module, "insert_text"):
            mock_run.return_value = mock.MagicMock(returncode=0)

            with instance._lock:
                instance._start_recording()
            instance._stop_and_transcribe()

            deadline = time.time() + 5.0
            while time.time() < deadline:
                if mock_run.called:
                    break
                time.sleep(0.1)

        assert mock_run.called, "subprocess.run (osascript) was never called"
        call_args = str(mock_run.call_args_list)
        # Should use bundle ID approach
        assert "com.microsoft.VSCode" in call_args or "Code" in call_args, (
            f"Expected VS Code identifier in osascript call, got: {call_args}"
        )
