"""
Keyboard shortcuts overlay — opened by pressing ?
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from . import theme

SHORTCUTS = [
    ("Navigation", [
        ("↑ / ↓",      "Move through all visible folders"),
        ("→",          "Expand folder (again: enter it)"),
        ("←",          "Go up to parent folder"),
        ("Enter",      "Jump to file list"),
        ("F",          "Focus search field"),
        ("V",          "Toggle flat / folder view"),
        ("Esc",        "Cancel search / back to tree"),
    ]),
    ("Playback", [
        ("Space",      "Play / stop current file"),
        ("Tab",        "Toggle autoplay"),
    ]),
    ("Set management", [
        ("E",          "Add selected file to active set"),
        ("Shift + E",  "Quick-add to a different set"),
        ("N",          "New set"),
        ("Q",          "Cycle to next set"),
        ("Delete",     "Remove selected set item"),
    ]),
    ("Panels", [
        ("C",          "Open waveform editor"),
        ("X",          "Open export panel"),
        ("Ctrl+T",     "Cycle colour theme"),
        ("?",          "Show this shortcuts list"),
        ("Esc",        "Close panel / go back"),
    ]),
]


class ShortcutsOverlay(tk.Toplevel):

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.title("Keyboard shortcuts")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.geometry("460x480")
        self._build()
        self.bind("<Escape>",         lambda _: self.destroy())
        self.bind("<question>",       lambda _: self.destroy())
        self.grab_set()

    def _build(self) -> None:
        ttk.Label(self, text="Keyboard shortcuts",
                  font=("Menlo", 13), foreground=theme.SEL_FG,
                  background=theme.BG).pack(anchor="w", padx=14, pady=(12, 6))

        outer = ttk.Frame(self, style="TFrame")
        outer.pack(fill="both", expand=True, padx=10, pady=4)

        # two-column layout
        col_l = ttk.Frame(outer, style="TFrame")
        col_r = ttk.Frame(outer, style="TFrame")
        col_l.pack(side="left", fill="y", expand=True, padx=(0, 8))
        col_r.pack(side="left", fill="y", expand=True)

        sections = SHORTCUTS
        for i, (section, rows) in enumerate(sections):
            col = col_l if i % 2 == 0 else col_r
            ttk.Label(col, text=section.upper(), style="Hint.TLabel",
                      font=theme.FONT_XS).pack(anchor="w", pady=(8, 3))
            for key, desc in rows:
                row = ttk.Frame(col, style="TFrame")
                row.pack(fill="x", pady=1)
                theme.kbd_label(row, text=key).pack(side="left")
                ttk.Label(row, text="  " + desc, style="Muted.TLabel",
                          font=theme.FONT_XS).pack(side="left")

        ttk.Button(self, text="Close  [Esc]",
                   command=self.destroy).pack(pady=10)
