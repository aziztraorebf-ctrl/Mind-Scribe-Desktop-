# tests/test_app_focus.py
"""Tests for _capture_previous_app() focus tracking logic in MindScribeApp."""
import os
import sys
import pytest
import unittest.mock as mock

os.environ.setdefault("MINDSCRIBE_TEST_DIR", "/tmp/ms_test_focus")


def make_mock_ns_app(name: str, bundle: str):
    """Create a mock object that mimics NSRunningApplication."""
    m = mock.MagicMock()
    m.localizedName.return_value = name
    m.bundleIdentifier.return_value = bundle
    return m


@pytest.fixture
def app_instance(tmp_path, monkeypatch):
    """MindScribeApp with all UI/audio/hotkey components mocked out."""
    monkeypatch.setenv("MINDSCRIBE_TEST_DIR", str(tmp_path))

    # Remove src.app from sys.modules so we get a fresh import each time
    for mod_name in list(sys.modules.keys()):
        if mod_name == "src.app" or mod_name.startswith("src.app."):
            del sys.modules[mod_name]

    with mock.patch("src.app.HotkeyManager"), \
         mock.patch("src.app.TrayIcon"), \
         mock.patch("src.app.RecordingOverlay"), \
         mock.patch("src.app.SettingsWindow"), \
         mock.patch("src.app.Dashboard"), \
         mock.patch("src.app.AudioRecorder"), \
         mock.patch("src.app.Transcriber"), \
         mock.patch("src.app.play_ready"), \
         mock.patch("src.app.play_record_start"), \
         mock.patch("src.app.play_record_stop"):
        from src.app import MindScribeApp
        instance = MindScribeApp()
        yield instance


class TestInitialState:
    def test_previous_app_starts_as_none(self, app_instance):
        """_previous_app must be None at startup."""
        assert app_instance._previous_app is None


class TestCaptureFilteringLogic:
    """Test the filtering logic inline, mirroring _capture_previous_app() exactly."""

    def _apply_filter(self, app_instance, ns_app):
        """
        Reproduce the filtering logic from _capture_previous_app() directly,
        without importing AppKit.  This tests the guard conditions in isolation.
        """
        if ns_app is None:
            return
        name = ns_app.localizedName() or ""
        bundle = ns_app.bundleIdentifier() or ""
        if "MindScribe" in name or bundle.startswith("com.mindscribe"):
            # Early return — do NOT update _previous_app
            return
        app_instance._previous_app = ns_app

    def test_stores_non_mindscribe_app(self, app_instance):
        """Non-MindScribe app should be stored in _previous_app."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        app_instance._previous_app = None

        self._apply_filter(app_instance, vscode)

        assert app_instance._previous_app is vscode
        assert app_instance._previous_app.localizedName() == "Code"

    def test_ignores_mindscribe_by_name(self, app_instance):
        """App with 'MindScribe' in name must NOT overwrite _previous_app."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        mindscribe = make_mock_ns_app("MindScribe Desktop", "local.mindscribe")
        app_instance._previous_app = vscode

        self._apply_filter(app_instance, mindscribe)

        assert app_instance._previous_app is vscode

    def test_ignores_mindscribe_by_bundle_prefix(self, app_instance):
        """App with bundle starting with 'com.mindscribe' must NOT overwrite."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        variant = make_mock_ns_app("AnyName", "com.mindscribe.helper")
        app_instance._previous_app = vscode

        self._apply_filter(app_instance, variant)

        assert app_instance._previous_app is vscode

    def test_ignores_none_candidate(self, app_instance):
        """None frontmost app must not crash and must not change _previous_app."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        app_instance._previous_app = vscode

        self._apply_filter(app_instance, None)

        assert app_instance._previous_app is vscode

    def test_overwrites_with_newer_non_mindscribe_app(self, app_instance):
        """Switching from Chrome to VS Code should update _previous_app."""
        chrome = make_mock_ns_app("Google Chrome", "com.google.Chrome")
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        app_instance._previous_app = chrome

        self._apply_filter(app_instance, vscode)

        assert app_instance._previous_app is vscode

    def test_mindscribe_name_case_sensitive(self, app_instance):
        """Lowercase 'mindscribe' in name should NOT be filtered (case-sensitive check)."""
        app_instance._previous_app = None
        lowercase_app = make_mock_ns_app("mindscribe-helper", "com.other.app")

        self._apply_filter(app_instance, lowercase_app)

        # "MindScribe" (capital M and S) not in "mindscribe-helper" — should be stored
        assert app_instance._previous_app is lowercase_app


class TestCapturePreviousAppViaMacOS:
    """Test _capture_previous_app() with AppKit mocked at the module level."""

    def test_stores_app_when_not_mindscribe(self, app_instance):
        """_capture_previous_app() stores a non-MindScribe frontmost app."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")

        mock_workspace = mock.MagicMock()
        mock_workspace.sharedWorkspace.return_value.frontmostApplication.return_value = vscode

        mock_appkit = mock.MagicMock()
        mock_appkit.NSWorkspace = mock_workspace

        import src.app as app_module
        original_is_macos = app_module._IS_MACOS
        app_module._IS_MACOS = True
        try:
            with mock.patch.dict(sys.modules, {"AppKit": mock_appkit}):
                app_instance._capture_previous_app()
        finally:
            app_module._IS_MACOS = original_is_macos

        assert app_instance._previous_app is vscode

    def test_does_not_store_mindscribe_app(self, app_instance):
        """_capture_previous_app() must not overwrite with a MindScribe window."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        app_instance._previous_app = vscode

        mindscribe_app = make_mock_ns_app("MindScribe Desktop", "local.mindscribe")

        mock_workspace = mock.MagicMock()
        mock_workspace.sharedWorkspace.return_value.frontmostApplication.return_value = mindscribe_app

        mock_appkit = mock.MagicMock()
        mock_appkit.NSWorkspace = mock_workspace

        import src.app as app_module
        original_is_macos = app_module._IS_MACOS
        app_module._IS_MACOS = True
        try:
            with mock.patch.dict(sys.modules, {"AppKit": mock_appkit}):
                app_instance._capture_previous_app()
        finally:
            app_module._IS_MACOS = original_is_macos

        assert app_instance._previous_app is vscode

    def test_skips_entirely_on_non_macos(self, app_instance):
        """_capture_previous_app() must be a no-op when _IS_MACOS is False."""
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        app_instance._previous_app = vscode

        import src.app as app_module
        original_is_macos = app_module._IS_MACOS
        app_module._IS_MACOS = False
        try:
            app_instance._capture_previous_app()
        finally:
            app_module._IS_MACOS = original_is_macos

        # _previous_app must remain unchanged
        assert app_instance._previous_app is vscode


class TestCaptureNotCalledWhenTranscribing:
    """Verify _capture_previous_app() is called inside state guard."""

    def test_capture_not_called_when_transcribing(self, app_instance):
        """When state is TRANSCRIBING, _on_hotkey_toggle must NOT call _capture_previous_app."""
        from src.app import AppState
        vscode = make_mock_ns_app("Code", "com.microsoft.VSCode")
        app_instance._previous_app = vscode

        # Force TRANSCRIBING state
        app_instance._state = AppState.TRANSCRIBING

        capture_calls = []
        original_capture = app_instance._capture_previous_app

        def spy():
            capture_calls.append(True)
            original_capture()

        app_instance._capture_previous_app = spy

        # Simulate hotkey toggle — should be a no-op in TRANSCRIBING state
        app_instance._on_hotkey_toggle()

        assert len(capture_calls) == 0, \
            f"_capture_previous_app was called {len(capture_calls)} time(s) during TRANSCRIBING"
        assert app_instance._previous_app is vscode, \
            f"_previous_app was changed to {app_instance._previous_app}"

    def test_capture_called_when_idle(self, app_instance):
        """When state is IDLE, _on_hotkey_toggle MUST call _capture_previous_app."""
        from src.app import AppState
        app_instance._state = AppState.IDLE

        capture_calls = []

        def spy():
            capture_calls.append(True)
            # No-op: don't actually call AppKit

        app_instance._capture_previous_app = spy
        # Also mock _start_recording to avoid side effects
        app_instance._start_recording = mock.MagicMock()

        app_instance._on_hotkey_toggle()

        assert len(capture_calls) == 1, \
            f"Expected _capture_previous_app to be called once, got {len(capture_calls)}"

    def test_capture_not_called_when_recording(self, app_instance):
        """When state is RECORDING, _on_hotkey_toggle calls _stop_and_transcribe, not capture."""
        from src.app import AppState
        app_instance._state = AppState.RECORDING

        capture_calls = []

        def spy():
            capture_calls.append(True)

        app_instance._capture_previous_app = spy
        app_instance._stop_and_transcribe = mock.MagicMock()

        app_instance._on_hotkey_toggle()

        assert len(capture_calls) == 0, \
            f"_capture_previous_app should not be called in RECORDING state"
