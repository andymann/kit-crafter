"""
Bottom detail pane: file info, BPM / key / pitch, tags, notes.
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk
from typing import Optional

from core.audio_engine import AudioEngine
from . import theme


class DetailPane(ttk.Frame):

    def __init__(self, parent: tk.Widget, engine: AudioEngine) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._engine = engine
        self._path: Optional[str] = None
        self._tags: list[str] = []
        self._build_ui()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        info = ttk.Frame(self, style="Panel.TFrame")
        info.grid(row=0, column=0, sticky="ew", padx=8, pady=4)

        # row 1: filename
        self._name_var = tk.StringVar(value="—")
        ttk.Label(info, textvariable=self._name_var, style="Accent.TLabel",
                  font=theme.FONT_S).pack(anchor="w")

        # row 2: technical fields
        fields = ttk.Frame(info, style="Panel.TFrame")
        fields.pack(anchor="w", pady=2)
        self._sr_var  = tk.StringVar(value="")
        self._ch_var  = tk.StringVar(value="")
        self._dur_var = tk.StringVar(value="")
        self._bpm_var = tk.StringVar(value="")
        self._key_var = tk.StringVar(value="")
        for label, var in [("sr", self._sr_var), ("ch", self._ch_var),
                            ("dur", self._dur_var), ("bpm", self._bpm_var),
                            ("key", self._key_var)]:
            ttk.Label(fields, text=label + ":", style="Hint.TLabel").pack(side="left", padx=(0, 2))
            ttk.Label(fields, textvariable=var, style="Muted.TLabel",
                      font=theme.FONT_XS).pack(side="left", padx=(0, 10))

        # tags
        tags_row = ttk.Frame(info, style="Panel.TFrame")
        tags_row.pack(anchor="w", pady=2)
        ttk.Label(tags_row, text="tags:", style="Hint.TLabel").pack(side="left", padx=(0, 4))
        self._tag_entry = ttk.Entry(tags_row, font=theme.FONT_XS, width=28)
        self._tag_entry.pack(side="left")
        self._tag_entry.bind("<Return>", self._save_tags)
        ttk.Button(tags_row, text="save", width=5,
                   command=self._save_tags).pack(side="left", padx=4)

        # right: transport hint
        hint = ttk.Frame(self, style="Panel.TFrame")
        hint.grid(row=0, column=1, sticky="e", padx=8)
        self._kbd_labels: list[tk.Label] = []
        for key, desc in [("F", "search"), ("Space", "play/stop"), ("E", "add to set"), ("C", "editor"), ("X", "export"), ("Ctrl+T", "switch theme")]:
            row = ttk.Frame(hint, style="Panel.TFrame")
            row.pack(anchor="e", pady=1)
            kl = theme.kbd_label(row, text=key)
            kl.pack(side="left", padx=(0, 4))
            self._kbd_labels.append(kl)
            ttk.Label(row, text=desc, style="Hint.TLabel").pack(side="left")

    # ------------------------------------------------------------------ update

    def set_file(self, path: str) -> None:
        self._path = path
        info = self._engine.file_info(path)
        self._name_var.set(os.path.basename(path))
        if info:
            sr = info.get("sr", 0)
            ch = info.get("channels", 0)
            dur = info.get("duration", 0.0)
            m, s = divmod(int(dur), 60)
            self._sr_var.set(f"{sr:,} Hz")
            self._ch_var.set("Mono" if ch == 1 else "Stereo" if ch == 2 else str(ch))
            self._dur_var.set(f"{m}:{s:02d}")
        else:
            for var in (self._sr_var, self._ch_var, self._dur_var):
                var.set("—")
        self._bpm_var.set("—")
        self._key_var.set("—")
        self._tag_entry.delete(0, "end")

    def clear(self) -> None:
        self._path = None
        for var in (self._name_var, self._sr_var, self._ch_var,
                    self._dur_var, self._bpm_var, self._key_var):
            var.set("—")
        self._tag_entry.delete(0, "end")

    def set_bpm_key(self, bpm: Optional[float], key: Optional[str]) -> None:
        self._bpm_var.set(f"{bpm:.1f}" if bpm else "—")
        self._key_var.set(key or "—")

    def apply_theme(self) -> None:
        for lbl in self._kbd_labels:
            lbl.configure(bg=theme.SURFACE, fg=theme.FG2)

    def _save_tags(self, _event=None) -> None:
        raw = self._tag_entry.get().strip()
        self._tags = [t.strip() for t in raw.split(",") if t.strip()]
