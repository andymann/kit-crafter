"""
Export pipeline.

Reads source audio, applies the clip region + fades, then processes
through the chain: mono → normalize → HPF → resample → bit-depth → write.
All heavy work runs in a background thread; progress is reported via callback.
"""
from __future__ import annotations
import os
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
import numpy as np

try:
    import soundfile as sf
    _SF = True
except ImportError:
    _SF = False

from .clip_model import Clip, FadeSpec

# ------------------------------------------------------------------ settings


@dataclass
class ExportSettings:
    output_dir: str = ""
    fmt: str = "WAV"              # WAV | AIFF | FLAC
    subtype: str = "PCM_16"       # PCM_16 | PCM_24 | PCM_32
    target_sr: int = 44100
    mono: bool = True
    normalize: bool = True
    normalize_db: float = -0.1    # dBFS ceiling
    hpf: bool = False
    hpf_freq: float = 40.0        # Hz
    limiter: bool = False


@dataclass
class ExportPreset:
    name: str
    settings: ExportSettings


BUILTIN_PRESETS: List[ExportPreset] = [
    ExportPreset("TR-8S",       ExportSettings(fmt="WAV", subtype="PCM_16", target_sr=44100, mono=True,  normalize=True)),
    ExportPreset("Octatrack",   ExportSettings(fmt="WAV", subtype="PCM_16", target_sr=44100, mono=False, normalize=True)),
    ExportPreset("SP-404 MK2",  ExportSettings(fmt="WAV", subtype="PCM_16", target_sr=44100, mono=False, normalize=True)),
    ExportPreset("DAW (24-bit)",ExportSettings(fmt="WAV", subtype="PCM_24", target_sr=48000, mono=False, normalize=False)),
]

# ------------------------------------------------------------------ processing helpers


def _apply_clip(data: np.ndarray, sr: int, clip: Optional[Clip]) -> np.ndarray:
    if clip is None or not clip.is_valid():
        return data
    start_frame = int(clip.start * sr)
    end_frame = int(clip.end * sr)
    return data[start_frame:end_frame]


def _apply_fades(data: np.ndarray, sr: int, fade: FadeSpec) -> np.ndarray:
    n = len(data)
    result = data.copy()
    fi = int(fade.fade_in * sr)
    fo = int(fade.fade_out * sr)
    if fi > 0 and fi <= n:
        env = np.linspace(0.0, 1.0, fi) ** fade.in_curve
        if result.ndim == 2:
            env = env[:, None]
        result[:fi] *= env
    if fo > 0 and fo <= n:
        env = np.linspace(1.0, 0.0, fo) ** fade.out_curve
        if result.ndim == 2:
            env = env[:, None]
        result[-fo:] *= env
    return result


def _to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        return data.mean(axis=1)
    return data


def _normalize(data: np.ndarray, ceiling_db: float) -> np.ndarray:
    peak = np.max(np.abs(data))
    if peak < 1e-9:
        return data
    target = 10 ** (ceiling_db / 20.0)
    return data * (target / peak)


def _highpass(data: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    """Simple first-order IIR high-pass filter."""
    rc = 1.0 / (2 * np.pi * cutoff_hz)
    dt = 1.0 / sr
    alpha = rc / (rc + dt)
    out = np.empty_like(data)
    if data.ndim == 1:
        out[0] = data[0]
        for i in range(1, len(data)):
            out[i] = alpha * (out[i - 1] + data[i] - data[i - 1])
    else:
        out[0] = data[0]
        for i in range(1, len(data)):
            out[i] = alpha * (out[i - 1] + data[i] - data[i - 1])
    return out


def _resample(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return data
    try:
        import librosa
        if data.ndim == 2:
            ch = [librosa.resample(data[:, c], orig_sr=src_sr, target_sr=dst_sr) for c in range(data.shape[1])]
            return np.stack(ch, axis=1)
        return librosa.resample(data, orig_sr=src_sr, target_sr=dst_sr)
    except ImportError:
        # fallback: linear interpolation (low quality, last resort)
        ratio = dst_sr / src_sr
        new_len = int(len(data) * ratio)
        x_old = np.linspace(0, 1, len(data))
        x_new = np.linspace(0, 1, new_len)
        if data.ndim == 2:
            return np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(data.shape[1])], axis=1)
        return np.interp(x_new, x_old, data)


# ------------------------------------------------------------------ exporter


def _ext_for_fmt(fmt: str) -> str:
    return {"WAV": ".wav", "AIFF": ".aiff", "FLAC": ".flac"}.get(fmt.upper(), ".wav")


def export_file(
    src_path: str,
    out_dir: str,
    out_name: str,
    settings: ExportSettings,
    clip: Optional[Clip] = None,
) -> Tuple[bool, str]:
    """
    Process one file and write to out_dir/out_name + extension.
    Returns (success, message).
    """
    if not _SF:
        return False, "soundfile not installed"
    try:
        data, sr = sf.read(src_path, dtype="float32", always_2d=True)

        # 1. clip
        if clip and clip.is_valid():
            data = _apply_clip(data, sr, clip)
            data = _apply_fades(data, sr, clip.fade)

        # 2. mono
        if settings.mono:
            data = _to_mono(data)

        # 3. resample
        if sr != settings.target_sr:
            data = _resample(data, sr, settings.target_sr)
            sr = settings.target_sr

        # 4. HPF
        if settings.hpf:
            data = _highpass(data, sr, settings.hpf_freq)

        # 5. normalize
        if settings.normalize:
            data = _normalize(data, settings.normalize_db)

        # 6. write
        ext = _ext_for_fmt(settings.fmt)
        out_path = os.path.join(out_dir, out_name + ext)
        os.makedirs(out_dir, exist_ok=True)
        sf.write(out_path, data, sr, subtype=settings.subtype)
        return True, out_path

    except Exception as exc:
        return False, str(exc)


class BatchExporter:
    """Run export_file on a list of (path, name, clip) tuples in a thread."""

    def __init__(
        self,
        items: List[Tuple[str, str, Optional[Clip]]],
        out_dir: str,
        settings: ExportSettings,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_done: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        self._items = items
        self._out_dir = out_dir
        self._settings = settings
        self._on_progress = on_progress
        self._on_done = on_done
        self._thread: Optional[threading.Thread] = None
        self.cancelled = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self.cancelled = True

    def _run(self) -> None:
        total = len(self._items)
        ok = 0
        for i, (path, name, clip) in enumerate(self._items):
            if self.cancelled:
                break
            success, msg = export_file(path, self._out_dir, name, self._settings, clip)
            if success:
                ok += 1
            if self._on_progress:
                self._on_progress(i + 1, total, msg)
        if self._on_done:
            self._on_done(ok, total)
