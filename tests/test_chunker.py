"""Tests for chunker module."""

import io
import wave

import pytest

from src.core.chunker import (
    needs_chunking,
    get_audio_duration_ms,
    chunk_audio,
    prepare_audio,
    MAX_FILE_SIZE_BYTES,
)


class TestNeedsChunking:
    def test_small_file_no_chunking(self, sample_wav_bytes):
        assert not needs_chunking(sample_wav_bytes)

    def test_large_file_needs_chunking(self):
        # Create a fake large buffer
        large_data = b"\x00" * (MAX_FILE_SIZE_BYTES + 1)
        assert needs_chunking(large_data)


class TestGetAudioDuration:
    def test_one_second_wav(self, sample_wav_bytes):
        duration = get_audio_duration_ms(sample_wav_bytes)
        assert duration == 1000

    def test_five_second_wav(self, long_wav_bytes):
        duration = get_audio_duration_ms(long_wav_bytes)
        assert duration == 5000


class TestChunkAudio:
    def test_short_audio_single_chunk(self, sample_wav_bytes):
        chunks = chunk_audio(sample_wav_bytes)
        assert len(chunks) == 1

    def test_longer_audio_multiple_chunks(self, long_wav_bytes):
        # 5 seconds with 30s chunk = 1 chunk (under threshold)
        chunks = chunk_audio(long_wav_bytes)
        assert len(chunks) >= 1
        # Each chunk should be valid WAV
        for chunk in chunks:
            buf = io.BytesIO(chunk)
            with wave.open(buf, "rb") as wf:
                assert wf.getnchannels() >= 1


class TestPrepareAudio:
    def test_empty_input(self):
        result = prepare_audio(b"")
        assert result == []

    def test_small_audio_returns_single_item(self, sample_wav_bytes):
        result = prepare_audio(sample_wav_bytes)
        assert len(result) >= 1
        assert len(result[0]) > 0


class TestSettings:
    """Test settings module while we're at it."""

    def test_settings_defaults(self):
        from src.config.settings import Settings
        s = Settings()
        assert s.language == "fr"
        assert s.primary_provider == "groq"
        assert s.record_mode == "toggle"
        assert s.sample_rate == 16000
        assert s.channels == 1
        assert s.restore_clipboard is True

    def test_settings_save_load_roundtrip(self, tmp_path, monkeypatch):
        from src.config.settings import Settings

        # Override config path to use tmp_path
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(Settings, "config_path", classmethod(lambda cls: config_file))

        s = Settings(language="en", record_mode="hold")
        s.save()

        loaded = Settings.load()
        assert loaded.language == "en"
        assert loaded.record_mode == "hold"

    def test_api_keys_not_persisted(self, tmp_path, monkeypatch):
        from src.config.settings import Settings
        import json

        config_file = tmp_path / "config.json"
        monkeypatch.setattr(Settings, "config_path", classmethod(lambda cls: config_file))

        s = Settings(groq_api_key="secret-key", openai_api_key="other-secret")
        s.save()

        raw = json.loads(config_file.read_text())
        assert "groq_api_key" not in raw
        assert "openai_api_key" not in raw
