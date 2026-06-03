"""
Audio playback engine.

Uses pygame.mixer for gapless, low-latency playback.
soundfile loads raw sample data for waveform rendering.
"""
from __future__ import annotations
import os
import threading
from typing import Callable, Optional
import numpy as np

try:
    import pygame
    _PYGAME = True
except ImportError:
    _PYGAME = False

try:
    import soundfile as sf
    _SF = True
except ImportError:
    _SF = False


class AudioEngine:
    """Singleton-style audio engine; create one per app."""

    AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".opus"}

    def __init__(self) -> None:
        if _PYGAME:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        self._current: Optional[str] = None
        self._on_stop: Optional[Callable] = None  # called when track ends naturally
        self._waveform_cache: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ playback

    def play(self, path: str) -> bool:
        if not _PYGAME or not os.path.isfile(path):
            return False
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self._current = path
            return True
        except Exception:
            return False

    def stop(self) -> None:
        if _PYGAME:
            pygame.mixer.music.stop()

    def toggle(self, path: Optional[str] = None) -> None:
        if _PYGAME and pygame.mixer.music.get_busy():
            self.stop()
        else:
            self.play(path or self._current or "")

    def is_playing(self) -> bool:
        return _PYGAME and bool(pygame.mixer.music.get_busy())

    @property
    def current(self) -> Optional[str]:
        return self._current

    # ------------------------------------------------------------------ waveform

    def load_waveform(self, path: str, n_points: int = 2000) -> Optional[np.ndarray]:
        """Return a mono float32 array downsampled to n_points for drawing."""
        if not _SF:
            return None
        with self._lock:
            cached = self._waveform_cache.get(path)
        if cached is not None:
            return cached
        try:
            data, _ = sf.read(path, dtype="float32", always_2d=True)
            mono = data.mean(axis=1)
            if len(mono) > n_points:
                step = max(1, len(mono) // n_points)
                mono = mono[::step][:n_points]
            with self._lock:
                self._waveform_cache[path] = mono
            return mono
        except Exception:
            return None

    def load_waveform_async(
        self, path: str, callback: Callable[[Optional[np.ndarray]], None]
    ) -> None:
        """Load waveform in a background thread, call callback on main thread."""
        def _worker():
            result = self.load_waveform(path)
            callback(result)
        threading.Thread(target=_worker, daemon=True).start()

    def clear_cache(self) -> None:
        with self._lock:
            self._waveform_cache.clear()

    # ------------------------------------------------------------------ meta

    @staticmethod
    def file_info(path: str) -> dict:
        """Return sr, channels, duration_sec, frames. Empty dict on error."""
        if not _SF:
            return {}
        try:
            info = sf.info(path)
            return {
                "sr": info.samplerate,
                "channels": info.channels,
                "frames": info.frames,
                "duration": info.frames / info.samplerate,
                "subtype": info.subtype,
            }
        except Exception:
            return {}

    def get_position(self) -> Optional[float]:
        """Return current playback position in seconds, or None if not playing."""
        if not _PYGAME:
            return None
        pos_ms = pygame.mixer.music.get_pos()
        return pos_ms / 1000.0 if pos_ms >= 0 else None

    @staticmethod
    def is_audio(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in AudioEngine.AUDIO_EXTS

    def cleanup(self) -> None:
        if _PYGAME:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
