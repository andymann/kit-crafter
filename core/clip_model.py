"""
Clip and fade metadata.

Clips are pure metadata — no audio is touched until export.
Each audio file can have one active clip; a full history is kept.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FadeSpec:
    """Fade-in and fade-out lengths in seconds, with curve exponent."""
    fade_in: float = 0.0    # seconds
    fade_out: float = 0.0   # seconds
    in_curve: float = 1.0   # 1.0 = linear, >1 concave, <1 convex
    out_curve: float = 1.0


@dataclass
class Clip:
    """A time region within an audio file (seconds)."""
    start: float        # seconds
    end: float          # seconds
    fade: FadeSpec = field(default_factory=FadeSpec)
    label: str = ""     # optional user label

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def is_valid(self) -> bool:
        return self.end > self.start and self.start >= 0


class ClipModel:
    """
    Stores the current clip and clip history for every file path.
    """

    def __init__(self) -> None:
        # path -> (active_clip, [history])
        self._data: Dict[str, tuple[Optional[Clip], List[Clip]]] = {}

    # ------------------------------------------------------------------ access

    def get_clip(self, path: str) -> Optional[Clip]:
        entry = self._data.get(path)
        return entry[0] if entry else None

    def get_history(self, path: str) -> List[Clip]:
        entry = self._data.get(path)
        return list(entry[1]) if entry else []

    def has_clip(self, path: str) -> bool:
        return self.get_clip(path) is not None

    # ------------------------------------------------------------------ editing

    def set_clip(self, path: str, start: float, end: float, fade: Optional[FadeSpec] = None) -> Clip:
        """Create or update the clip for a file. Previous clip is pushed to history."""
        clip = Clip(start=start, end=end, fade=fade or FadeSpec())
        prev_clip, history = self._data.get(path, (None, []))
        if prev_clip and prev_clip.is_valid():
            history = [prev_clip] + history
        self._data[path] = (clip, history)
        return clip

    def update_fade(self, path: str, fade: FadeSpec) -> None:
        clip = self.get_clip(path)
        if clip:
            clip.fade = fade
        else:
            # store fade without a clip region (full file with fades)
            entry = self._data.get(path, (None, []))
            self._data[path] = (Clip(start=0.0, end=0.0, fade=fade), entry[1])

    def clear_clip(self, path: str) -> None:
        entry = self._data.get(path)
        if entry and entry[0]:
            self._data[path] = (None, [entry[0]] + entry[1])

    def restore_from_history(self, path: str, index: int) -> Optional[Clip]:
        entry = self._data.get(path)
        if not entry:
            return None
        active, history = entry
        if index < 0 or index >= len(history):
            return None
        old = history.pop(index)
        if active:
            history.insert(0, active)
        self._data[path] = (old, history)
        return old

    # ------------------------------------------------------------------ bulk

    def all_paths_with_clips(self) -> List[str]:
        return [p for p, (c, _) in self._data.items() if c and c.is_valid()]
