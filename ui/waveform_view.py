"""
Canvas-based waveform display used in both the detail pane (mini) and editor (full).
"""
from __future__ import annotations
import tkinter as tk
from typing import Optional
import numpy as np
from . import theme


class WaveformCanvas(tk.Canvas):
    """
    Draws an audio waveform. Supports:
    - Mini mode: just the waveform, no interaction.
    - Editor mode: draggable clip region (top half) and zoom/pan (bottom half).
    """

    CLIP_COLOR      = "#5aadff"
    CLIP_FILL       = "#1e3a5f"
    WAVE_COLOR      = "#888888"
    WAVE_SEL_COLOR  = "#aaaaaa"
    PLAY_COLOR      = "#4aff88"
    FADE_COLOR      = "#ffaa44"

    def __init__(self, parent: tk.Widget, editor_mode: bool = False, **kw) -> None:
        kw.setdefault("bg", theme.PANEL)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("relief", "flat")
        super().__init__(parent, **kw)

        self._editor = editor_mode
        self._data: Optional[np.ndarray] = None   # normalised float32 [-1..1]
        self._sr: int = 44100
        self._duration: float = 0.0

        # clip region in normalised [0..1] coords of the waveform
        self._clip_start: Optional[float] = None
        self._clip_end:   Optional[float] = None
        self._drag_origin: Optional[float] = None

        # fade handles (normalised 0..1 within clip)
        self._fade_in_len:  float = 0.0
        self._fade_out_len: float = 0.0

        # zoom / pan (bottom half)
        self._view_start: float = 0.0    # normalised
        self._view_end:   float = 1.0

        # playhead
        self._playhead: Optional[float] = None

        # callbacks
        self.on_clip_change = None    # (start_s, end_s, fade_in_s, fade_out_s)

        if editor_mode:
            self.bind("<ButtonPress-1>",   self._mouse_press)
            self.bind("<B1-Motion>",       self._mouse_drag)
            self.bind("<ButtonRelease-1>", self._mouse_release)

        self.bind("<Configure>", lambda _e: self._redraw())

    # ------------------------------------------------------------------ data

    def set_waveform(self, data: Optional[np.ndarray], sr: int = 44100,
                     duration: Optional[float] = None) -> None:
        self._data = data
        self._sr = sr
        if duration is not None:
            self._duration = duration
        else:
            self._duration = len(data) / sr if data is not None else 0.0
        self._redraw()

    def set_clip(self, start_s: float, end_s: float,
                 fade_in_s: float = 0.0, fade_out_s: float = 0.0) -> None:
        if self._duration > 0:
            self._clip_start  = start_s  / self._duration
            self._clip_end    = end_s    / self._duration
            self._fade_in_len = fade_in_s  / max(end_s - start_s, 1e-9)
            self._fade_out_len= fade_out_s / max(end_s - start_s, 1e-9)
            self._redraw()

    def clear_clip(self) -> None:
        self._clip_start = self._clip_end = None
        self._fade_in_len = self._fade_out_len = 0.0
        self._redraw()

    def set_playhead(self, pos_s: Optional[float]) -> None:
        self._playhead = (pos_s / self._duration) if (pos_s is not None and self._duration > 0) else None
        self._redraw()

    # ------------------------------------------------------------------ drawing

    def _redraw(self) -> None:
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        self.delete("all")

        if self._editor:
            mid = int(h * 0.65)
            self._draw_wave_region(0, 0, w, mid)
            self._draw_overview(0, mid, w, h - mid)
        else:
            self._draw_wave_region(0, 0, w, h)

    def _draw_wave_region(self, x0: int, y0: int, w: int, h: int) -> None:
        cx = x0 + w / 2
        cy = y0 + h / 2

        # clip fill
        if self._clip_start is not None and self._clip_end is not None:
            lx = x0 + self._clip_start * w
            rx = x0 + self._clip_end * w
            self.create_rectangle(lx, y0, rx, y0 + h, fill=self.CLIP_FILL, outline="")
            self.create_line(lx, y0, lx, y0 + h, fill=self.CLIP_COLOR, width=1)
            self.create_line(rx, y0, rx, y0 + h, fill=self.CLIP_COLOR, width=1)

            # fade overlays
            clip_w = rx - lx
            if self._fade_in_len > 0:
                fi_x = lx + self._fade_in_len * clip_w
                self.create_rectangle(lx, y0, fi_x, y0 + h,
                                      fill="#1a3050", outline="",
                                      stipple="gray25")
                self.create_line(lx, y0 + h, fi_x, y0,
                                 fill=self.FADE_COLOR, width=1, dash=(3, 3))

            if self._fade_out_len > 0:
                fo_x = rx - self._fade_out_len * clip_w
                self.create_rectangle(fo_x, y0, rx, y0 + h,
                                      fill="#1a3050", outline="",
                                      stipple="gray25")
                self.create_line(fo_x, y0, rx, y0 + h,
                                 fill=self.FADE_COLOR, width=1, dash=(3, 3))

        # waveform bars
        if self._data is not None and len(self._data) > 0:
            data = self._data
            n = len(data)
            bar_w = max(1, w // n)
            step = max(1, n // w)
            xs = np.arange(0, w, bar_w)
            indices = (xs / w * n).astype(int)
            indices = np.clip(indices, 0, n - 1)
            amplitudes = np.abs(data[indices])
            for i, (px, amp) in enumerate(zip(xs, amplitudes)):
                bar_h = max(1, amp * (h / 2) * 0.9)
                color = (self.WAVE_SEL_COLOR
                         if (self._clip_start is not None
                             and self._clip_start <= px / w <= self._clip_end)
                         else self.WAVE_COLOR)
                mid_y = y0 + h / 2
                self.create_line(x0 + px, mid_y - bar_h,
                                 x0 + px, mid_y + bar_h,
                                 fill=color, width=max(1, bar_w - 1))
        else:
            # empty state
            self.create_text(cx, cy, text="no waveform", fill=theme.FG3,
                             font=theme.FONT_XS)

        # playhead
        if self._playhead is not None:
            px = x0 + self._playhead * w
            self.create_line(px, y0, px, y0 + h,
                             fill=self.PLAY_COLOR, width=1)

    def _draw_overview(self, x0: int, y0: int, w: int, h: int) -> None:
        """Zoomed-out overview strip (bottom in editor mode)."""
        self.create_rectangle(x0, y0, x0 + w, y0 + h,
                              fill=theme.BG, outline=theme.BORDER)
        if self._data is not None and len(self._data) > 0:
            n = len(self._data)
            for px in range(w):
                idx = int(px / w * n)
                amp = abs(self._data[min(idx, n - 1)])
                bh = max(1, amp * (h / 2) * 0.85)
                cy = y0 + h / 2
                self.create_line(x0 + px, cy - bh, x0 + px, cy + bh,
                                 fill=theme.FG3, width=1)

        # viewport highlight
        vx0 = x0 + self._view_start * w
        vx1 = x0 + self._view_end * w
        self.create_rectangle(vx0, y0, vx1, y0 + h,
                              fill="#1e3050", outline=self.CLIP_COLOR,
                              stipple="gray50")

    # ------------------------------------------------------------------ interaction (editor only)

    def _clip_top_half(self, y: int) -> bool:
        h = self.winfo_height()
        return y < h * 0.65

    def _mouse_press(self, event: tk.Event) -> None:
        w = self.winfo_width()
        self._drag_origin = event.x / w
        if self._clip_top_half(event.y):
            self._clip_start = self._drag_origin
            self._clip_end   = self._drag_origin

    def _mouse_drag(self, event: tk.Event) -> None:
        w = self.winfo_width()
        pos = max(0.0, min(1.0, event.x / w))
        if self._clip_top_half(event.y) and self._drag_origin is not None:
            a, b = sorted([self._drag_origin, pos])
            self._clip_start = a
            self._clip_end   = b
            self._redraw()

    def _mouse_release(self, event: tk.Event) -> None:
        if (self._clip_top_half(event.y)
                and self._clip_start is not None
                and self._clip_end is not None
                and self.on_clip_change
                and self._duration > 0):
            self.on_clip_change(
                self._clip_start * self._duration,
                self._clip_end   * self._duration,
                self._fade_in_len  * (self._clip_end - self._clip_start) * self._duration,
                self._fade_out_len * (self._clip_end - self._clip_start) * self._duration,
            )
        self._drag_origin = None
