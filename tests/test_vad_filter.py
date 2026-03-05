"""Tests for VAD (Voice Activity Detection) audio filtering."""

import io
import math
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from src.core.vad_filter import filter_silence


def _make_wav(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Helper: pack numpy int16 samples into WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


def _make_silence(duration_s: float = 2.0, sample_rate: int = 16000) -> bytes:
    """WAV of pure silence."""
    samples = np.zeros(int(duration_s * sample_rate), dtype=np.int16)
    return _make_wav(samples)


def _make_audio(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    """WAV of a sine wave (used as generic non-empty audio)."""
    n = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, n)
    samples = (np.sin(2 * math.pi * 440 * t) * 16000).astype(np.int16)
    return _make_wav(samples)


def _make_audio_with_silence(sample_rate: int = 16000) -> bytes:
    """WAV: 1s silence + 1s audio + 1s silence."""
    silence = np.zeros(sample_rate, dtype=np.int16)
    t = np.linspace(0, 1.0, sample_rate)
    audio = (np.sin(2 * math.pi * 440 * t) * 16000).astype(np.int16)
    combined = np.concatenate([silence, audio, silence])
    return _make_wav(combined)


def _mock_model_and_fn(speech_segments):
    """Return (mock_model, mock_get_speech_timestamps) for patching."""
    mock_model = MagicMock()
    mock_fn = MagicMock(return_value=speech_segments)
    return mock_model, mock_fn


class TestFilterSilence:
    def test_returns_bytes(self):
        """filter_silence must always return bytes."""
        result = filter_silence(_make_audio())
        assert isinstance(result, bytes)

    def test_empty_input_returns_empty(self):
        """Empty bytes input should return empty bytes safely."""
        result = filter_silence(b"")
        assert result == b""

    def test_pure_silence_returns_empty(self):
        """Pure silence should return empty bytes (nothing to transcribe)."""
        result = filter_silence(_make_silence(duration_s=2.0))
        assert result == b""

    def test_speech_passes_through(self):
        """When VAD detects speech, the result must be non-empty."""
        wav_in = _make_audio(duration_s=1.0)
        sample_count = 16000  # 1s at 16kHz

        mock_model, mock_fn = _mock_model_and_fn(
            [{"start": 0, "end": sample_count}]
        )
        with patch("src.core.vad_filter._vad_model", mock_model), \
             patch("src.core.vad_filter._get_speech_timestamps_fn", mock_fn):
            result = filter_silence(wav_in)

        assert result != b""

    def test_speech_shorter_than_input(self):
        """When silence is stripped, output WAV is shorter than input."""
        wav_in = _make_audio_with_silence()
        # Input: 3s (silence + audio + silence). Simulate VAD keeping only middle 1s.
        speech_start = 16000
        speech_end = 32000

        mock_model, mock_fn = _mock_model_and_fn(
            [{"start": speech_start, "end": speech_end}]
        )
        with patch("src.core.vad_filter._vad_model", mock_model), \
             patch("src.core.vad_filter._get_speech_timestamps_fn", mock_fn):
            wav_out = filter_silence(wav_in)

        assert len(wav_out) < len(wav_in)

    def test_output_is_valid_wav(self):
        """Output must be valid 16kHz mono int16 WAV."""
        wav_in = _make_audio(duration_s=1.0)
        sample_count = 16000

        mock_model, mock_fn = _mock_model_and_fn(
            [{"start": 0, "end": sample_count}]
        )
        with patch("src.core.vad_filter._vad_model", mock_model), \
             patch("src.core.vad_filter._get_speech_timestamps_fn", mock_fn):
            result = filter_silence(wav_in)

        assert result != b""
        buf = io.BytesIO(result)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000

    def test_vad_unavailable_returns_original(self):
        """If VAD model fails to load, original audio is returned (graceful degradation)."""
        wav_in = _make_audio(duration_s=1.0)
        with patch("src.core.vad_filter._vad_model", None), \
             patch("src.core.vad_filter._get_speech_timestamps_fn", None), \
             patch("src.core.vad_filter._get_model", return_value=(None, None)):
            result = filter_silence(wav_in)
        assert result == wav_in
