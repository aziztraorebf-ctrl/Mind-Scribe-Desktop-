"""Unified transcription client with Groq (primary) and OpenAI (fallback)."""

import io
import logging
import time

from groq import Groq
from openai import OpenAI

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when all transcription providers fail."""


class Transcriber:
    """Transcribes audio using Groq Whisper API with OpenAI fallback."""

    def __init__(
        self,
        groq_api_key: str = "",
        openai_api_key: str = "",
        primary_provider: str = "groq",
        model: str = "whisper-large-v3",
        language: str = "fr",
        prompt: str = "",
    ):
        self.primary_provider = primary_provider
        self.model = model
        self.language = language
        self.prompt = prompt

        self._groq: Groq | None = None
        self._openai: OpenAI | None = None

        if groq_api_key:
            self._groq = Groq(api_key=groq_api_key)
        if openai_api_key:
            self._openai = OpenAI(api_key=openai_api_key)

    @property
    def has_groq(self) -> bool:
        return self._groq is not None

    @property
    def has_openai(self) -> bool:
        return self._openai is not None

    @property
    def is_configured(self) -> bool:
        return self.has_groq or self.has_openai

    def transcribe(self, audio_wav: bytes, max_retries: int = 3) -> str:
        """Transcribe WAV audio bytes to text.

        Tries the primary provider first, then falls back to the other.
        Each provider is retried up to max_retries times with exponential backoff.
        """
        if not self.is_configured:
            raise TranscriptionError("No API keys configured. Set GROQ_API_KEY or OPENAI_API_KEY.")

        providers = self._get_provider_order()
        last_error: Exception | None = None

        for provider_name, provider_fn in providers:
            try:
                return self._try_with_retries(provider_name, provider_fn, audio_wav, max_retries)
            except Exception as exc:
                last_error = exc
                logger.warning("Provider %s failed: %s. Trying next.", provider_name, exc)

        raise TranscriptionError(f"All providers failed. Last error: {last_error}")

    def _get_provider_order(self) -> list[tuple[str, object]]:
        """Return providers in priority order."""
        providers = []

        if self.primary_provider == "groq":
            if self._groq:
                providers.append(("groq", self._transcribe_groq))
            if self._openai:
                providers.append(("openai", self._transcribe_openai))
        else:
            if self._openai:
                providers.append(("openai", self._transcribe_openai))
            if self._groq:
                providers.append(("groq", self._transcribe_groq))

        return providers

    def _try_with_retries(
        self,
        name: str,
        fn: object,
        audio_wav: bytes,
        max_retries: int,
    ) -> str:
        """Try a provider function with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return fn(audio_wav)
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.info("Retry %d/%d for %s after %ds: %s", attempt + 1, max_retries, name, wait, exc)
                time.sleep(wait)

    def _transcribe_groq(self, audio_wav: bytes) -> str:
        """Transcribe using Groq Whisper API."""
        audio_file = io.BytesIO(audio_wav)
        audio_file.name = "recording.wav"

        response = self._groq.audio.transcriptions.create(
            file=audio_file,
            model=self.model,
            language=self.language,
            prompt=self.prompt or None,
            response_format="text",
        )

        text = str(response).strip()
        if not text:
            raise TranscriptionError("Groq returned empty transcription")
        return text

    def _transcribe_openai(self, audio_wav: bytes) -> str:
        """Transcribe using OpenAI Whisper API."""
        audio_file = io.BytesIO(audio_wav)
        audio_file.name = "recording.wav"

        response = self._openai.audio.transcriptions.create(
            file=audio_file,
            model="whisper-1",
            language=self.language,
            prompt=self.prompt or None,
            response_format="text",
        )

        text = str(response).strip()
        if not text:
            raise TranscriptionError("OpenAI returned empty transcription")
        return text
