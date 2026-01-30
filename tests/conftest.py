"""Shared test fixtures for MindScribe Desktop."""

import io
import struct
import sys
from pathlib import Path

import pytest

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_wav_bytes() -> bytes:
    """Generate a minimal valid WAV file with 1 second of silence (16kHz mono)."""
    sample_rate = 16000
    channels = 1
    duration_s = 1
    num_frames = sample_rate * duration_s

    buf = io.BytesIO()
    import wave
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        # Write silence (zeros)
        wf.writeframes(b"\x00\x00" * num_frames)

    return buf.getvalue()


@pytest.fixture
def sample_wav_with_tone() -> bytes:
    """Generate a WAV file with a 440Hz tone (1 second, 16kHz mono)."""
    import math
    sample_rate = 16000
    channels = 1
    duration_s = 1
    freq = 440
    num_frames = sample_rate * duration_s

    # Generate sine wave
    samples = []
    for i in range(num_frames):
        value = int(32767 * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.append(struct.pack("<h", value))

    buf = io.BytesIO()
    import wave
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(samples))

    return buf.getvalue()


@pytest.fixture
def long_wav_bytes() -> bytes:
    """Generate a 5-second WAV file (larger for chunking tests)."""
    sample_rate = 16000
    channels = 1
    duration_s = 5
    num_frames = sample_rate * duration_s

    buf = io.BytesIO()
    import wave
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)

    return buf.getvalue()
