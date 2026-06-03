"""
Right-hand active-set panel.

Shows the current set's items, a tab strip for switching sets,
and the history dropdown for restored items.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, simpledialog
from typing import Callable, Optional

from core.set_manager import SetManager, SampleSet
from core.clip_model import ClipModel
from . import theme


class SetPanel(ttk.Frame):

    def __init__(
        self,
        parent: tk.Widget,
        set_mgr: SetManager,
        clip_model: ClipModel,
        on_open_export: Optional[Callable] = None,
        on_play: Optional[Callable[[str], None]] = None,
        on_select: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._mgr        = set_mgr
        self._clips      = clip_model
        self._on_export  = on_open_export
        self._on_play    = on_play
        self._on_select  = on_select
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # header
        hdr = ttk.Frame(self, style="Panel.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        ttk.Label(hdr, text="ACTIVE SET", style="Muted.TLabel",
                  font=theme.FONT_XS).pack(side="left")
        ttk.Button(hdr, text="N", width=2, command=self._new_set).pack(side="right", padx=2)
        ttk.Button(hdr, text="Q", width=2, command=self._cycle_set).pack(side="right")

        # set tabs (scrollable strip)
        self._tabs_frame = ttk.Frame(self, style="Panel.TFrame")
        self._tabs_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=2)

        # item list
        list_frame = ttk.Frame(self, style="Panel.TFrame")
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            list_frame,
            bg=theme.PANEL, fg=theme.FG, font=theme.FONT_S,
            selectbackground=theme.SEL, selectforeground=theme.SEL_FG,
            relief="flat", highlightthickness=0, activestyle="none",
            borderwidth=0,
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_frame, orient="vertical",
                           command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)
        self._listbox.bind("<Double-1>", self._play_selected)
        self._listbox.bind("<Delete>",   self._remove_selected)
        self._listbox.bind("<BackSpace>", self._remove_selected)

        # history
        hist_frame = ttk.Frame(self, style="Panel.TFrame")
        hist_frame.grid(row=3, column=0, sticky="ew", padx=4, pady=2)
        ttk.Label(hist_frame, text="history", style="Hint.TLabel").pack(side="left")
        self._hist_btn = ttk.Button(hist_frame, text="▾", width=2,
                                     command=self._show_history)
        self._hist_btn.pack(side="right")

        # export button
        exp_frame = ttk.Frame(self, style="Panel.TFrame")
        exp_frame.grid(row=4, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(exp_frame, text="Export set [X]", style="Accent.TButton",
                   command=self._open_export).pack(fill="x")

    # ------------------------------------------------------------------ refresh

    def refresh(self) -> None:
        self._refresh_tabs()
        self._refresh_list()

    def _refresh_tabs(self) -> None:
        for w in self._tabs_frame.winfo_children():
            w.destroy()
        active_id = self._mgr.active.id
        for s in self._mgr.sets:
            btn = tk.Button(
                self._tabs_frame,
                text=s.name,
                bg=theme.SEL if s.id == active_id else theme.SURFACE,
                fg=theme.SEL_FG if s.id == active_id else theme.FG2,
                font=theme.FONT_XS,
                relief="flat", bd=0, padx=5, pady=2,
                command=lambda sid=s.id: self._activate(sid),
            )
            btn.pack(side="left", padx=2)

    def _refresh_list(self) -> None:
        self._listbox.delete(0, "end")
        for item in self._mgr.active.items:
            has_clip = self._clips.has_clip(item.path)
            badge = " ✂" if has_clip else ""
            self._listbox.insert("end", item.name + badge)

    # ------------------------------------------------------------------ actions

    def _new_set(self) -> None:
        name = simpledialog.askstring("New set", "Set name:",
                                       initialvalue=f"Set {len(self._mgr.sets)+1}")
        if name:
            self._mgr.new_set(name)
            self.refresh()

    def _cycle_set(self) -> None:
        self._mgr.cycle_active()
        self.refresh()

    def _activate(self, set_id: str) -> None:
        self._mgr.set_active(set_id)
        self.refresh()

    def _on_listbox_select(self, _event=None) -> None:
        idx = self._listbox.curselection()
        if not idx or not self._on_select:
            return
        item = self._mgr.active.items[idx[0]]
        self._on_select(item.path)

    def _play_selected(self, _event=None) -> None:
        idx = self._listbox.curselection()
        if not idx:
            return
        item = self._mgr.active.items[idx[0]]
        if self._on_play:
            self._on_play(item.path)

    def _remove_selected(self, _event=None) -> None:
        idx = self._listbox.curselection()
        if not idx:
            return
        item = self._mgr.active.items[idx[0]]
        self._mgr.remove_from_active(item.path)
        self.refresh()

    def _show_history(self) -> None:
        hist = self._mgr.active.history
        if not hist:
            return
        popup = tk.Toplevel(self)
        popup.title("History")
        popup.configure(bg=theme.PANEL)
        popup.geometry("260x220")
        lbl = ttk.Label(popup, text="Removed items — double-click to restore",
                         style="Muted.TLabel")
        lbl.pack(padx=8, pady=(8, 4))
        lb = tk.Listbox(popup, bg=theme.PANEL, fg=theme.FG, font=theme.FONT_S,
                         selectbackground=theme.SEL, relief="flat",
                         highlightthickness=0)
        lb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        for item in hist:
            lb.insert("end", item.name)

        def restore(_event=None):
            sel = lb.curselection()
            if not sel:
                return
            item = hist[sel[0]]
            self._mgr.active.restore(item.path)
            self.refresh()
            popup.destroy()

        lb.bind("<Double-1>", restore)

    def _open_export(self) -> None:
        if self._on_export:
            self._on_export()

    # ------------------------------------------------------------------ public

    def apply_theme(self) -> None:
        self.refresh()   # rebuilds tab buttons with current theme colours
        self._listbox.configure(
            bg=theme.PANEL, fg=theme.FG,
            selectbackground=theme.SEL, selectforeground=theme.SEL_FG,
        )

    def add_file(self, path: str, name: str) -> bool:
        ok = self._mgr.add_to_active(path, name)
        self.refresh()
        return ok

    def add_file_to(self, set_id: str, path: str, name: str) -> bool:
        ok = self._mgr.add_to_set(set_id, path, name)
        self.refresh()
        return ok

    def show_quick_add(self, path: str, name: str) -> None:
        """Show a popup to pick which set to add to."""
        popup = tk.Toplevel(self)
        popup.title("Quick-add to set")
        popup.configure(bg=theme.PANEL)
        popup.geometry("220x160")
        ttk.Label(popup, text="Choose a set:", style="Muted.TLabel").pack(pady=(8, 4))
        lb = tk.Listbox(popup, bg=theme.PANEL, fg=theme.FG, font=theme.FONT_S,
                         selectbackground=theme.SEL, relief="flat",
                         highlightthickness=0)
        lb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        sets = self._mgr.sets
        for s in sets:
            lb.insert("end", s.name)

        def confirm(_event=None):
            sel = lb.curselection()
            if not sel:
                return
            self.add_file_to(sets[sel[0]].id, path, name)
            popup.destroy()

        lb.bind("<Double-1>", confirm)
        ttk.Button(popup, text="Add", command=confirm).pack(pady=4)
