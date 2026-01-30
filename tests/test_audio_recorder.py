"""Tests for audio_recorder module."""

import wave
import io

import pytest

from src.core.audio_recorder import AudioRecorder, RecorderState


class TestAudioRecorderInit:
    def test_default_state_is_idle(self):
        recorder = AudioRecorder()
        assert recorder.state == RecorderState.IDLE
        assert not recorder.is_recording

    def test_custom_parameters(self):
        recorder = AudioRecorder(sample_rate=44100, channels=2, device=1)
        assert recorder.sample_rate == 44100
        assert recorder.channels == 2
        assert recorder.device == 1

    def test_duration_is_zero_initially(self):
        recorder = AudioRecorder()
        assert recorder.duration_seconds == 0.0


class TestAudioRecorderOperations:
    def test_stop_without_start_returns_empty(self):
        recorder = AudioRecorder()
        result = recorder.stop()
        assert result == b""

    def test_cancel_resets_state(self):
        recorder = AudioRecorder()
        recorder.cancel()
        assert recorder.state == RecorderState.IDLE


class TestListDevices:
    def test_list_devices_returns_list(self):
        devices = AudioRecorder.list_devices()
        assert isinstance(devices, list)
        # Each device should have expected keys
        for dev in devices:
            assert "index" in dev
            assert "name" in dev
            assert "channels" in dev


class TestWavOutput:
    def test_valid_wav_format(self, sample_wav_bytes):
        """Verify fixture produces valid WAV."""
        buf = io.BytesIO(sample_wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 16000  # 1 second
