"""Audio chunking for long recordings exceeding API file size limits."""

import io
import logging
import wave

from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Groq API limit for direct upload
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

# Optimal chunk duration for Whisper accuracy
CHUNK_DURATION_MS = 30_000  # 30 seconds

# Overlap to avoid cutting words at boundaries
OVERLAP_MS = 1_000  # 1 second


def needs_chunking(wav_data: bytes) -> bool:
    """Check if the WAV data exceeds the API file size limit."""
    return len(wav_data) > MAX_FILE_SIZE_BYTES


def wav_to_mp3(wav_data: bytes, bitrate: str = "64k") -> bytes:
    """Compress WAV to MP3 to reduce file size (~10x reduction).

    Uses 64k bitrate (sufficient for speech, Whisper doesn't need higher).
    """
    audio = AudioSegment.from_wav(io.BytesIO(wav_data))
    buf = io.BytesIO()
    audio.export(buf, format="mp3", bitrate=bitrate)
    return buf.getvalue()


def chunk_audio(wav_data: bytes) -> list[bytes]:
    """Split WAV audio into smaller WAV chunks for sequential transcription.

    Each chunk is CHUNK_DURATION_MS long with OVERLAP_MS overlap.
    Returns list of WAV byte buffers.
    """
    audio = AudioSegment.from_wav(io.BytesIO(wav_data))
    total_ms = len(audio)
    chunks = []
    start = 0

    while start < total_ms:
        end = min(start + CHUNK_DURATION_MS, total_ms)
        segment = audio[start:end]

        buf = io.BytesIO()
        segment.export(buf, format="wav")
        chunks.append(buf.getvalue())

        # Move forward by chunk duration minus overlap
        start += CHUNK_DURATION_MS - OVERLAP_MS

    logger.info(
        "Split %d ms audio into %d chunks of ~%d ms",
        total_ms,
        len(chunks),
        CHUNK_DURATION_MS,
    )
    return chunks


def prepare_audio(wav_data: bytes) -> list[bytes]:
    """Prepare audio for transcription API.

    For short audio (<25MB): try MP3 compression first, return single chunk.
    For long audio (>25MB after compression): split into chunks.
    Returns list of audio byte buffers ready for API upload.
    """
    if not wav_data:
        return []

    # Try MP3 compression first
    try:
        mp3_data = wav_to_mp3(wav_data)
        if len(mp3_data) <= MAX_FILE_SIZE_BYTES:
            logger.info(
                "Compressed WAV (%d KB) to MP3 (%d KB), single upload",
                len(wav_data) // 1024,
                len(mp3_data) // 1024,
            )
            return [mp3_data]
    except Exception as exc:
        logger.warning("MP3 compression failed, using WAV chunks: %s", exc)

    # MP3 still too large or compression failed: chunk the WAV
    if not needs_chunking(wav_data):
        return [wav_data]

    return chunk_audio(wav_data)


def get_audio_duration_ms(wav_data: bytes) -> int:
    """Get duration of WAV audio in milliseconds."""
    with wave.open(io.BytesIO(wav_data), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return int(frames / rate * 1000)
