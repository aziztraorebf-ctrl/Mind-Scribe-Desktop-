"""Audio recording using sounddevice with WAV output."""

import io
import math
import threading
import time
import wave
from collections import deque
from enum import Enum, auto

import numpy as np
import sounddevice as sd

# Number of recent RMS values to keep for waveform display
_LEVEL_HISTORY_SIZE = 48


class RecorderState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()


class AudioRecorder:
    """Records audio from the microphone into a WAV buffer."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: int | None = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self._state = RecorderState.IDLE
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

        # Real-time audio level monitoring
        self._current_rms: float = 0.0
        self._level_history: deque[float] = deque(maxlen=_LEVEL_HISTORY_SIZE)
        self._record_start_time: float = 0.0
        self._elapsed_before_pause: float = 0.0

    @property
    def state(self) -> RecorderState:
        return self._state

    @property
    def is_recording(self) -> bool:
        return self._state == RecorderState.RECORDING

    @property
    def duration_seconds(self) -> float:
        """Estimated duration of recorded audio in seconds."""
        if self._state == RecorderState.IDLE:
            with self._lock:
                total_frames = sum(f.shape[0] for f in self._frames)
            return total_frames / self.sample_rate
        if self._state == RecorderState.PAUSED:
            # Frozen at the moment pause was pressed
            return self._elapsed_before_pause
        # While recording, accumulated time + current segment
        return self._elapsed_before_pause + (time.monotonic() - self._record_start_time)

    @property
    def current_rms(self) -> float:
        """Current audio input RMS level (0.0 to 1.0, normalized)."""
        return self._current_rms

    @property
    def level_history(self) -> list[float]:
        """Recent RMS levels for waveform display (newest last)."""
        return list(self._level_history)

    def start(self) -> None:
        """Start recording audio from the microphone."""
        if self._state != RecorderState.IDLE:
            return

        self._frames = []
        self._current_rms = 0.0
        self._level_history.clear()
        self._record_start_time = time.monotonic()
        self._elapsed_before_pause = 0.0
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=self.device,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._state = RecorderState.RECORDING

    def stop(self) -> bytes:
        """Stop recording and return WAV data as bytes."""
        if self._state == RecorderState.IDLE:
            return b""

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._state = RecorderState.IDLE
        return self._build_wav()

    def pause(self) -> None:
        """Pause recording (keeps buffer)."""
        if self._state == RecorderState.RECORDING and self._stream is not None:
            self._stream.stop()
            # Freeze the timer: accumulate elapsed time from current segment
            self._elapsed_before_pause += time.monotonic() - self._record_start_time
            self._state = RecorderState.PAUSED

    def resume(self) -> None:
        """Resume a paused recording."""
        if self._state == RecorderState.PAUSED and self._stream is not None:
            # Reset segment start so duration_seconds continues from frozen value
            self._record_start_time = time.monotonic()
            self._stream.start()
            self._state = RecorderState.RECORDING

    def cancel(self) -> None:
        """Cancel recording and discard buffer."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._frames = []
        self._state = RecorderState.IDLE

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback invoked by sounddevice for each audio block."""
        if status:
            # Log dropped frames, but don't crash
            pass
        data = indata.copy()
        with self._lock:
            self._frames.append(data)

        # Compute RMS level (normalized 0.0-1.0 for int16 range)
        # Amplification factor of 12x makes waveform visible even with distant microphones
        rms_raw = math.sqrt(float(np.mean(data.astype(np.float64) ** 2)))
        rms_normalized = min(1.0, rms_raw / 32768.0 * 12.0)
        self._current_rms = rms_normalized
        self._level_history.append(rms_normalized)

    def _build_wav(self) -> bytes:
        """Combine recorded frames into a WAV byte buffer."""
        with self._lock:
            if not self._frames:
                return b""
            audio_data = np.concatenate(self._frames, axis=0)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())

        return buf.getvalue()

    @staticmethod
    def list_devices() -> list[dict]:
        """Return a list of available input audio devices."""
        devices = sd.query_devices()
        result = []
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                result.append({
                    "index": idx,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "sample_rate": dev["default_samplerate"],
                })
        return result
