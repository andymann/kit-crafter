"""
Dark colour palettes and ttk style configuration for Kit Crafter.
Call apply(root) once on startup; use cycle(root) to switch palettes.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

# ------------------------------------------------------------------ palettes

_PALETTES: dict[str, dict] = {
    "Classic": {
        "BG":        "#1a1a1a",
        "PANEL":     "#222222",
        "SURFACE":   "#2a2a2a",
        "BORDER":    "#333333",
        "SEL":       "#1e3a5f",
        "SEL_FG":    "#5aadff",
        "FG":        "#d8d8d8",
        "FG2":       "#888888",
        "FG3":       "#555555",
        "GREEN":     "#4aff88",
        "ORANGE":    "#ffaa44",
        "RED":       "#ff5555",
        "HOVER":     "#363636",
        "PRESSED":   "#1e1e1e",
        "SEL_HOVER": "#1a2e45",
    },
    "Amethyst": {
        "BG":        "#0d0c10",
        "PANEL":     "#13111a",
        "SURFACE":   "#1c1926",
        "BORDER":    "#2d2840",
        "SEL":       "#2a1f4e",
        "SEL_FG":    "#a78bfa",
        "FG":        "#ede9f6",
        "FG2":       "#7c6e9a",
        "FG3":       "#4a4060",
        "GREEN":     "#6ee7b7",
        "ORANGE":    "#fbbf24",
        "RED":       "#f87171",
        "HOVER":     "#262233",
        "PRESSED":   "#0f0d16",
        "SEL_HOVER": "#3b2d6e",
    },
    "Neon": {
        "BG":        "#090812",
        "PANEL":     "#0e0c1a",
        "SURFACE":   "#161325",
        "BORDER":    "#232040",
        "SEL":       "#200a3e",
        "SEL_FG":    "#f72585",
        "FG":        "#f0ecff",
        "FG2":       "#7a60b0",
        "FG3":       "#4a3575",
        "GREEN":     "#06ffa5",
        "ORANGE":    "#ffbe0b",
        "RED":       "#ff3355",
        "HOVER":     "#1d1535",
        "PRESSED":   "#0b0916",
        "SEL_HOVER": "#3c0f68",
    },
    "Midnight": {
        "BG":        "#0b0f1c",
        "PANEL":     "#101520",
        "SURFACE":   "#17202e",
        "BORDER":    "#1e2c40",
        "SEL":       "#1a2e4a",
        "SEL_FG":    "#58b8f8",
        "FG":        "#c6d8ee",
        "FG2":       "#4e7090",
        "FG3":       "#2c4260",
        "GREEN":     "#3ddbb8",
        "ORANGE":    "#f5a832",
        "RED":       "#f05570",
        "HOVER":     "#141c2c",
        "PRESSED":   "#080c18",
        "SEL_HOVER": "#1e3654",
    },
}

_current_theme: str = "Classic"

# ------------------------------------------------------------------ module-level colour vars
# Read throughout the app as `theme.SEL_FG` etc.  Updated on every cycle().

BG        = _PALETTES["Classic"]["BG"]
PANEL     = _PALETTES["Classic"]["PANEL"]
SURFACE   = _PALETTES["Classic"]["SURFACE"]
BORDER    = _PALETTES["Classic"]["BORDER"]
SEL       = _PALETTES["Classic"]["SEL"]
SEL_FG    = _PALETTES["Classic"]["SEL_FG"]
FG        = _PALETTES["Classic"]["FG"]
FG2       = _PALETTES["Classic"]["FG2"]
FG3       = _PALETTES["Classic"]["FG3"]
GREEN     = _PALETTES["Classic"]["GREEN"]
ORANGE    = _PALETTES["Classic"]["ORANGE"]
RED       = _PALETTES["Classic"]["RED"]
HOVER     = _PALETTES["Classic"]["HOVER"]
PRESSED   = _PALETTES["Classic"]["PRESSED"]
SEL_HOVER = _PALETTES["Classic"]["SEL_HOVER"]

FONT    = ("Menlo", 11)
FONT_S  = ("Menlo", 10)
FONT_XS = ("Menlo", 9)


# ------------------------------------------------------------------ theme API

def current() -> str:
    return _current_theme


def set_theme(name: str, root: tk.Tk) -> None:
    """Switch to a specific named theme and re-apply styles."""
    global _current_theme
    if name not in _PALETTES:
        return
    _current_theme = name
    _load_palette(name)
    apply(root)


def cycle(root: tk.Tk) -> str:
    """Advance to the next palette, update globals, re-apply styles.
    Returns the new theme name."""
    global _current_theme
    names = list(_PALETTES.keys())
    _current_theme = names[(names.index(_current_theme) + 1) % len(names)]
    _load_palette(_current_theme)
    apply(root)
    return _current_theme


def _load_palette(name: str) -> None:
    global BG, PANEL, SURFACE, BORDER, SEL, SEL_FG, FG, FG2, FG3
    global GREEN, ORANGE, RED, HOVER, PRESSED, SEL_HOVER
    p = _PALETTES[name]
    BG        = p["BG"]
    PANEL     = p["PANEL"]
    SURFACE   = p["SURFACE"]
    BORDER    = p["BORDER"]
    SEL       = p["SEL"]
    SEL_FG    = p["SEL_FG"]
    FG        = p["FG"]
    FG2       = p["FG2"]
    FG3       = p["FG3"]
    GREEN     = p["GREEN"]
    ORANGE    = p["ORANGE"]
    RED       = p["RED"]
    HOVER     = p["HOVER"]
    PRESSED   = p["PRESSED"]
    SEL_HOVER = p["SEL_HOVER"]


# ------------------------------------------------------------------ style application

def apply(root: tk.Tk) -> None:
    """Apply (or re-apply) the current palette to the root window and ttk styles."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, font=FONT,
                    troughcolor=PANEL, fieldbackground=PANEL,
                    selectbackground=SEL, selectforeground=SEL_FG,
                    bordercolor=BORDER, highlightthickness=0, relief="flat")

    style.configure("TFrame",            background=BG)
    style.configure("Panel.TFrame",      background=PANEL)
    style.configure("Surface.TFrame",    background=SURFACE)

    style.configure("TLabel",        background=BG,    foreground=FG,     font=FONT)
    style.configure("Muted.TLabel",  foreground=FG2)
    style.configure("Hint.TLabel",   foreground=FG3,   font=FONT_XS)
    style.configure("Accent.TLabel", foreground=SEL_FG, font=FONT)
    style.configure("Green.TLabel",  foreground=GREEN,  font=FONT_S)

    style.configure("TButton",
                    background=SURFACE, foreground=FG, font=FONT_S,
                    relief="flat", padding=(6, 3), borderwidth=1, bordercolor=BORDER)
    style.map("TButton",
              background=[("active", HOVER), ("pressed", PRESSED)],
              foreground=[("active", FG)])

    style.configure("Accent.TButton", foreground=SEL_FG, bordercolor=SEL_FG)
    style.map("Accent.TButton", background=[("active", SEL_HOVER)])

    style.configure("TEntry",
                    fieldbackground=SURFACE, foreground=FG, insertcolor=FG,
                    font=FONT_S, relief="flat", padding=(4, 2), bordercolor=BORDER)
    style.configure("Placeholder.TEntry",
                    fieldbackground=SURFACE, foreground=FG3, insertcolor=FG,
                    font=FONT_S, relief="flat", padding=(4, 2), bordercolor=BORDER)

    style.configure("TScrollbar",
                    background=PANEL, troughcolor=BG, arrowcolor=FG2,
                    bordercolor=BG, relief="flat", width=8)
    style.map("TScrollbar", background=[("active", SURFACE)])

    style.configure("Treeview",
                    background=PANEL, foreground=FG, fieldbackground=PANEL,
                    font=FONT_S, rowheight=24, borderwidth=0, relief="flat")
    style.configure("Treeview.Heading",
                    background=BG, foreground=FG2, font=FONT_XS,
                    relief="flat", padding=(4, 2))
    style.map("Treeview",
              background=[("selected", SEL)],
              foreground=[("selected", SEL_FG)])

    style.configure("TSeparator", background=BORDER)

    style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT_S)
    style.map("TCheckbutton", background=[("active", BG)])

    style.configure("TCombobox",
                    fieldbackground=SURFACE, foreground=FG, font=FONT_S,
                    selectbackground=SEL, selectforeground=SEL_FG,
                    background=SURFACE, arrowcolor=FG2)
    style.map("TCombobox",
              fieldbackground=[("readonly", SURFACE)],
              foreground=[("readonly", FG)])

    style.configure("TLabelframe",
                    background=BG, foreground=FG2, font=FONT_XS,
                    bordercolor=BORDER, relief="flat")
    style.configure("TLabelframe.Label", background=BG, foreground=FG2, font=FONT_XS)

    root.update_idletasks()


def kbd_label(parent: tk.Widget, text: str, **kw) -> tk.Label:
    """Small keyboard shortcut badge widget."""
    return tk.Label(
        parent, text=text,
        bg=SURFACE, fg=FG2,
        font=FONT_XS, relief="flat",
        padx=3, pady=1,
        **kw,
    )
