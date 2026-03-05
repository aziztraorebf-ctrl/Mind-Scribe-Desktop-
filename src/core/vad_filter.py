"""Voice Activity Detection filter using Silero VAD.

Strips silent segments from WAV audio before sending to transcription API.
Returns empty bytes if no speech detected (saves API calls and prevents
Whisper hallucinations on silent audio).
"""

import io
import logging
import wave

import numpy as np

logger = logging.getLogger(__name__)

_SPEECH_THRESHOLD = 0.5
_MIN_SPEECH_DURATION_MS = 250
_MIN_SILENCE_DURATION_MS = 100

_vad_model = None
_get_speech_timestamps_fn = None


def _get_model():
    global _vad_model, _get_speech_timestamps_fn
    if _vad_model is None:
        try:
            from silero_vad import load_silero_vad, get_speech_timestamps
            _vad_model = load_silero_vad()
            _get_speech_timestamps_fn = get_speech_timestamps
            logger.info("Silero VAD model loaded")
        except Exception as exc:
            logger.warning("Could not load Silero VAD: %s — VAD disabled", exc)
    return _vad_model, _get_speech_timestamps_fn


def filter_silence(wav_bytes: bytes) -> bytes:
    """Remove silent segments from WAV audio.

    Args:
        wav_bytes: Raw WAV bytes (16kHz, mono, int16).

    Returns:
        WAV bytes with silence stripped, or empty bytes if no speech found.
        Falls back to returning original audio if VAD fails.
    """
    if not wav_bytes:
        return b""

    model, get_speech_timestamps = _get_model()

    if model is None:
        logger.debug("VAD unavailable, returning original audio")
        return wav_bytes

    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                logger.warning(
                    "VAD expects mono 16-bit WAV, got ch=%d sw=%d",
                    wf.getnchannels(), wf.getsampwidth(),
                )
                return wav_bytes
            raw = wf.readframes(wf.getnframes())
            sample_rate = wf.getframerate()

        import torch
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(samples)

        speech_segments = get_speech_timestamps(
            audio_tensor,
            model,
            sampling_rate=sample_rate,
            threshold=_SPEECH_THRESHOLD,
            min_speech_duration_ms=_MIN_SPEECH_DURATION_MS,
            min_silence_duration_ms=_MIN_SILENCE_DURATION_MS,
        )

        if not speech_segments:
            logger.info("VAD: no speech detected, skipping transcription")
            return b""

        segments = [samples[seg["start"]: seg["end"]] for seg in speech_segments]
        speech_audio = np.concatenate(segments)

        original_duration = len(samples) / sample_rate
        filtered_duration = len(speech_audio) / sample_rate
        logger.info(
            "VAD: kept %.1fs of speech from %.1fs recording (%.0f%% stripped)",
            filtered_duration,
            original_duration,
            (1 - filtered_duration / original_duration) * 100,
        )

        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes((speech_audio * 32768.0).astype(np.int16).tobytes())

        return out_buf.getvalue()

    except Exception as exc:
        logger.warning("VAD processing failed: %s — returning original audio", exc)
        return wav_bytes
