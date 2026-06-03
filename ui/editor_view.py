"""
Full-screen waveform editor.

Activated by pressing C in the browser; dismissed with Esc.
Exposes clip region drag (top half) and zoom/pan (bottom half).
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from core.audio_engine import AudioEngine
from core.clip_model import ClipModel, FadeSpec
from .waveform_view import WaveformCanvas
from . import theme


class EditorView(ttk.Frame):

    def __init__(
        self,
        parent: tk.Widget,
        engine: AudioEngine,
        clip_model: ClipModel,
        on_close: Optional[Callable] = None,
    ) -> None:
        super().__init__(parent, style="TFrame")
        self._engine = engine
        self._clips  = clip_model
        self._on_close = on_close
        self._path: Optional[str] = None
        self._tracking: bool = False

        # clip state
        self._start_s  = 0.0
        self._end_s    = 0.0
        self._fade_in  = 0.0
        self._fade_out = 0.0

        self._build_ui()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # header
        hdr = ttk.Frame(self, style="Panel.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        self._title_var = tk.StringVar(value="editor")
        ttk.Label(hdr, textvariable=self._title_var,
                  style="Accent.TLabel").pack(side="left")
        ttk.Button(hdr, text="Esc / close", command=self._close).pack(side="right")

        # waveform (editor mode = True)
        self._wave = WaveformCanvas(self, editor_mode=True, height=280)
        self._wave.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        self._wave.on_clip_change = self._on_clip_drag

        # fade controls
        fade_frame = ttk.Frame(self, style="Panel.TFrame")
        fade_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=2)
        ttk.Label(fade_frame, text="fade-in (s):", style="Muted.TLabel").pack(side="left")
        self._fi_var = tk.DoubleVar(value=0.0)
        ttk.Scale(fade_frame, from_=0.0, to=2.0, orient="horizontal",
                  variable=self._fi_var, length=100,
                  command=self._fade_changed).pack(side="left", padx=4)
        self._fi_lbl = ttk.Label(fade_frame, text="0.00", style="Muted.TLabel")
        self._fi_lbl.pack(side="left", padx=(0, 16))

        ttk.Label(fade_frame, text="fade-out (s):", style="Muted.TLabel").pack(side="left")
        self._fo_var = tk.DoubleVar(value=0.0)
        ttk.Scale(fade_frame, from_=0.0, to=2.0, orient="horizontal",
                  variable=self._fo_var, length=100,
                  command=self._fade_changed).pack(side="left", padx=4)
        self._fo_lbl = ttk.Label(fade_frame, text="0.00", style="Muted.TLabel")
        self._fo_lbl.pack(side="left")

        # clip info + actions
        act = ttk.Frame(self, style="Panel.TFrame")
        act.grid(row=3, column=0, sticky="ew", padx=8, pady=6)
        self._clip_info = tk.StringVar(value="no clip set — drag on waveform to create one")
        ttk.Label(act, textvariable=self._clip_info, style="Hint.TLabel").pack(side="left")

        ttk.Button(act, text="▶ Preview", command=self._preview,
                   style="Accent.TButton").pack(side="right", padx=4)
        ttk.Button(act, text="Clear clip", command=self._clear_clip).pack(side="right")
        ttk.Button(act, text="Save clip", command=self._save_clip,
                   style="Accent.TButton").pack(side="right", padx=4)

        # history
        self._hist_var = tk.StringVar(value="history: 0 clips")
        ttk.Label(act, textvariable=self._hist_var, style="Hint.TLabel").pack(side="right", padx=8)

    # ------------------------------------------------------------------ load

    def load(self, path: str) -> None:
        self._path = path
        self._title_var.set(os.path.basename(path))

        # load waveform async
        def _on_wave(data):
            info = self._engine.file_info(path)
            sr = info.get("sr", 44100) if info else 44100
            duration = info.get("duration") if info else None
            self._wave.set_waveform(data, sr, duration)

        self._engine.load_waveform_async(path, _on_wave)

        # restore existing clip
        clip = self._clips.get_clip(path)
        if clip and clip.is_valid():
            self._start_s  = clip.start
            self._end_s    = clip.end
            self._fade_in  = clip.fade.fade_in
            self._fade_out = clip.fade.fade_out
            self._fi_var.set(self._fade_in)
            self._fo_var.set(self._fade_out)
            self._wave.set_clip(self._start_s, self._end_s,
                                self._fade_in, self._fade_out)
            self._update_info()
        else:
            self._wave.clear_clip()
            self._clip_info.set("no clip — drag on waveform to create one")

        # history count
        hist = self._clips.get_history(path)
        self._hist_var.set(f"history: {len(hist)} clip{'s' if len(hist) != 1 else ''}")

        # start playhead tracking loop for this editor session
        if not self._tracking:
            self._tracking = True
            self._tick_playhead()

    # ------------------------------------------------------------------ callbacks

    def _on_clip_drag(self, start: float, end: float,
                      fade_in: float, fade_out: float) -> None:
        self._start_s  = start
        self._end_s    = end
        # don't override fade sliders from drag — only update waveform
        self._wave.set_clip(start, end, self._fi_var.get(), self._fo_var.get())
        self._update_info()

    def _fade_changed(self, _val=None) -> None:
        self._fade_in  = round(self._fi_var.get(), 2)
        self._fade_out = round(self._fo_var.get(), 2)
        self._fi_lbl.configure(text=f"{self._fade_in:.2f}")
        self._fo_lbl.configure(text=f"{self._fade_out:.2f}")
        self._wave.set_clip(self._start_s, self._end_s,
                            self._fade_in, self._fade_out)

    def _update_info(self) -> None:
        dur = self._end_s - self._start_s
        self._clip_info.set(
            f"start {self._start_s:.3f}s   end {self._end_s:.3f}s   "
            f"len {dur:.3f}s"
        )

    # ------------------------------------------------------------------ playhead

    def _tick_playhead(self) -> None:
        if not self._tracking:
            return
        if self._path and self._engine.is_playing() and self._engine.current == self._path:
            pos = self._engine.get_position()
            self._wave.set_playhead(pos)
        else:
            self._wave.set_playhead(None)
        self.after(40, self._tick_playhead)   # ~25 fps

    # ------------------------------------------------------------------ actions

    def _save_clip(self) -> None:
        if not self._path or self._end_s <= self._start_s:
            return
        fade = FadeSpec(
            fade_in=self._fi_var.get(),
            fade_out=self._fo_var.get(),
        )
        self._clips.set_clip(self._path, self._start_s, self._end_s, fade)
        hist = self._clips.get_history(self._path)
        self._hist_var.set(f"history: {len(hist)} clip{'s' if len(hist) != 1 else ''}")

    def _clear_clip(self) -> None:
        if self._path:
            self._clips.clear_clip(self._path)
        self._wave.clear_clip()
        self._start_s = self._end_s = 0.0
        self._clip_info.set("clip cleared")

    def _preview(self) -> None:
        if self._path:
            self._engine.play(self._path)

    def _close(self) -> None:
        self._tracking = False
        self._wave.set_playhead(None)
        if self._on_close:
            self._on_close()
