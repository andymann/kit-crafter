"""
Export panel — opened by pressing X.

Shows as a Toplevel dialog. Runs the batch export in a background thread
and updates a progress bar.
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from core.set_manager import SetManager
from core.clip_model import ClipModel
from core.exporter import (
    ExportSettings, ExportPreset, BatchExporter, BUILTIN_PRESETS
)
from . import theme


class ExportPanel(tk.Toplevel):

    def __init__(
        self,
        parent: tk.Widget,
        set_mgr: SetManager,
        clip_model: ClipModel,
    ) -> None:
        super().__init__(parent)
        self.title("Export")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.geometry("460x440")

        self._mgr    = set_mgr
        self._clips  = clip_model
        self._exporter: Optional[BatchExporter] = None

        # settings vars
        self._out_dir    = tk.StringVar(value=os.path.expanduser("~/Desktop/SampleScout"))
        self._fmt        = tk.StringVar(value="WAV")
        self._subtype    = tk.StringVar(value="PCM_16")
        self._sr         = tk.StringVar(value="44100")
        self._mono       = tk.BooleanVar(value=True)
        self._normalize  = tk.BooleanVar(value=True)
        self._norm_db    = tk.DoubleVar(value=-0.1)
        self._hpf        = tk.BooleanVar(value=False)
        self._hpf_freq   = tk.DoubleVar(value=40.0)
        self._limiter    = tk.BooleanVar(value=False)

        self._user_presets: list[ExportPreset] = []

        self._build_ui()
        self.grab_set()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="Export settings",
                  font=theme.FONT, foreground=theme.FG,
                  background=theme.BG).grid(row=0, column=0, columnspan=3,
                                             sticky="w", padx=10, pady=(10, 4))

        # ---- preset strip ----
        preset_frame = ttk.Frame(self, style="Panel.TFrame")
        preset_frame.grid(row=1, column=0, columnspan=3, sticky="ew",
                          padx=10, pady=2)
        ttk.Label(preset_frame, text="Presets:", style="Muted.TLabel").pack(side="left")
        for p in BUILTIN_PRESETS:
            btn = tk.Button(
                preset_frame, text=p.name, bg=theme.SURFACE, fg=theme.FG2,
                font=theme.FONT_XS, relief="flat", bd=0, padx=6, pady=2,
                command=lambda preset=p: self._apply_preset(preset),
            )
            btn.pack(side="left", padx=2)

        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=4)

        # ---- settings grid ----
        self._row = 3
        self._settings_grid(self)

        ttk.Separator(self, orient="horizontal").grid(
            row=14, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        # ---- output dir ----
        ttk.Label(self, text="Output folder:", style="Muted.TLabel",
                  background=theme.BG).grid(row=15, column=0, sticky="w", padx=10)
        ttk.Entry(self, textvariable=self._out_dir, width=28,
                  font=theme.FONT_S).grid(row=15, column=1, sticky="ew", padx=4)
        ttk.Button(self, text="…",
                   command=self._browse_dir).grid(row=15, column=2, padx=6)

        # ---- progress + export btn ----
        self._progress = ttk.Progressbar(self, orient="horizontal",
                                          mode="determinate", length=300)
        self._progress.grid(row=16, column=0, columnspan=2,
                            padx=10, pady=(10, 4), sticky="ew")
        self._status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._status_var, style="Hint.TLabel",
                  background=theme.BG).grid(row=17, column=0, columnspan=3,
                                             padx=10, sticky="w")
        ttk.Button(self, text="Export set", style="Accent.TButton",
                   command=self._start_export).grid(row=18, column=0,
                                                     columnspan=3,
                                                     padx=10, pady=8, sticky="ew")

        self.columnconfigure(1, weight=1)

    def _settings_grid(self, parent: tk.Widget) -> None:
        def row(label, widget_factory, r):
            ttk.Label(parent, text=label, style="Muted.TLabel",
                      background=theme.BG).grid(row=r, column=0, sticky="w", padx=10, pady=2)
            w = widget_factory(parent)
            w.grid(row=r, column=1, sticky="w", padx=4, pady=2)

        row("Mono",       lambda p: ttk.Checkbutton(p, variable=self._mono,    style="TCheckbutton"), 3)
        row("Normalize",  lambda p: ttk.Checkbutton(p, variable=self._normalize,style="TCheckbutton"), 4)
        row("Peak (dBFS)",lambda p: ttk.Entry(p, textvariable=self._norm_db, width=8, font=theme.FONT_S), 5)
        row("High-pass",  lambda p: ttk.Checkbutton(p, variable=self._hpf,    style="TCheckbutton"), 6)
        row("HPF freq",   lambda p: ttk.Entry(p, textvariable=self._hpf_freq, width=8, font=theme.FONT_S), 7)
        row("Limiter",    lambda p: ttk.Checkbutton(p, variable=self._limiter, style="TCheckbutton"), 8)
        row("Format",     lambda p: ttk.Combobox(p, textvariable=self._fmt,
                                                  values=["WAV","AIFF","FLAC"],
                                                  state="readonly", width=10,
                                                  font=theme.FONT_S), 9)
        row("Bit depth",  lambda p: ttk.Combobox(p, textvariable=self._subtype,
                                                  values=["PCM_16","PCM_24","PCM_32"],
                                                  state="readonly", width=10,
                                                  font=theme.FONT_S), 10)
        row("Sample rate",lambda p: ttk.Combobox(p, textvariable=self._sr,
                                                  values=["22050","44100","48000","96000"],
                                                  state="readonly", width=10,
                                                  font=theme.FONT_S), 11)

    # ------------------------------------------------------------------ actions

    def _apply_preset(self, preset: ExportPreset) -> None:
        s = preset.settings
        self._fmt.set(s.fmt)
        self._subtype.set(s.subtype)
        self._sr.set(str(s.target_sr))
        self._mono.set(s.mono)
        self._normalize.set(s.normalize)
        self._norm_db.set(s.normalize_db)
        self._hpf.set(s.hpf)

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self._out_dir.set(path)

    def _build_settings(self) -> ExportSettings:
        return ExportSettings(
            output_dir  = self._out_dir.get(),
            fmt         = self._fmt.get(),
            subtype     = self._subtype.get(),
            target_sr   = int(self._sr.get()),
            mono        = self._mono.get(),
            normalize   = self._normalize.get(),
            normalize_db= float(self._norm_db.get()),
            hpf         = self._hpf.get(),
            hpf_freq    = float(self._hpf_freq.get()),
            limiter     = self._limiter.get(),
        )

    def _start_export(self) -> None:
        active = self._mgr.active
        if not active.items:
            messagebox.showinfo("Export", "Active set is empty.", parent=self)
            return

        settings = self._build_settings()
        out_dir  = settings.output_dir
        if not out_dir:
            messagebox.showwarning("Export", "Please choose an output folder.", parent=self)
            return

        items = [
            (item.path, item.name, self._clips.get_clip(item.path))
            for item in active.items
        ]

        total = len(items)
        self._progress["maximum"] = total
        self._progress["value"]   = 0

        def _progress(done, tot, msg):
            self.after(0, lambda: self._on_progress(done, tot, msg))

        def _done(ok, tot):
            self.after(0, lambda: self._on_done(ok, tot))

        self._exporter = BatchExporter(
            items=items,
            out_dir=out_dir,
            settings=settings,
            on_progress=_progress,
            on_done=_done,
        )
        self._exporter.start()
        self._status_var.set(f"Exporting 0 / {total}…")

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self._progress["value"] = done
        self._status_var.set(f"{done} / {total}  {os.path.basename(msg)}")

    def _on_done(self, ok: int, total: int) -> None:
        self._status_var.set(f"Done: {ok}/{total} files exported.")
        self._progress["value"] = total
        messagebox.showinfo("Export complete",
                            f"{ok} of {total} files exported to:\n{self._out_dir.get()}",
                            parent=self)
