"""Tests for transcriber module."""

import pytest

from src.core.transcriber import Transcriber, TranscriptionError


class TestTranscriberInit:
    def test_no_keys_not_configured(self):
        t = Transcriber()
        assert not t.is_configured
        assert not t.has_groq
        assert not t.has_openai

    def test_groq_key_configured(self):
        t = Transcriber(groq_api_key="test-key")
        assert t.is_configured
        assert t.has_groq
        assert not t.has_openai

    def test_openai_key_configured(self):
        t = Transcriber(openai_api_key="test-key")
        assert t.is_configured
        assert not t.has_groq
        assert t.has_openai

    def test_both_keys_configured(self):
        t = Transcriber(groq_api_key="g-key", openai_api_key="o-key")
        assert t.is_configured
        assert t.has_groq
        assert t.has_openai


class TestTranscriberErrors:
    def test_transcribe_without_keys_raises(self, sample_wav_bytes):
        t = Transcriber()
        with pytest.raises(TranscriptionError, match="No API keys configured"):
            t.transcribe(sample_wav_bytes)


class TestProviderOrder:
    def test_groq_primary_order(self):
        t = Transcriber(groq_api_key="g", openai_api_key="o", primary_provider="groq")
        order = t._get_provider_order()
        assert order[0][0] == "groq"
        assert order[1][0] == "openai"

    def test_openai_primary_order(self):
        t = Transcriber(groq_api_key="g", openai_api_key="o", primary_provider="openai")
        order = t._get_provider_order()
        assert order[0][0] == "openai"
        assert order[1][0] == "groq"

    def test_single_provider_only(self):
        t = Transcriber(groq_api_key="g", primary_provider="groq")
        order = t._get_provider_order()
        assert len(order) == 1
        assert order[0][0] == "groq"
