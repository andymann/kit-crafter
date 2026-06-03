"""
Browser panel: folder tree (left) + file list (right).

Keyboard navigation — tree has focus by default:
  ↑ / ↓   — move between sibling directories on the same level
  →        — expand selected directory (second press enters first child)
  ←        — go up to parent directory
  Enter    — jump to file list (top file selected)

  In the file list:
  ↑ / ↓   — move up / down through files
  V        — toggle flat / folder view
  Space    — play / stop
  E        — add selected file to active set
  Shift+E  — quick-add to another set (shows picker)
"""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from core.file_scanner import FileScanner, DirNode
from core.audio_engine import AudioEngine
from . import theme


class BrowserPanel(ttk.Frame):

    def __init__(
        self,
        parent: tk.Widget,
        scanner: FileScanner,
        engine: AudioEngine,
        on_select: Optional[Callable[[DirNode], None]] = None,
        on_add_to_set: Optional[Callable[[DirNode], None]] = None,
        on_quick_add: Optional[Callable[[DirNode], None]] = None,
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._scanner  = scanner
        self._engine   = engine
        self._on_select   = on_select
        self._on_add      = on_add_to_set
        self._on_quick    = on_quick_add
        self._autoplay    = False
        self._current_node: Optional[DirNode] = None
        self._search_placeholder_active = False

        # Numeric IIDs avoid Tcl special-character issues ([, ], spaces in paths)
        self._iid_counter: int = 0
        self._tree_iid_to_path: Dict[str, str] = {}   # tree IID → fs path
        self._list_iid_to_node: Dict[str, DirNode] = {}  # list IID → DirNode
        self._list_populate_id: int = 0

        self._build_ui()
        self._show_search_placeholder()
        self._refresh_tree()

    def _next_iid(self) -> str:
        self._iid_counter += 1
        return str(self._iid_counter)

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self, style="Panel.TFrame")
        bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(bar, textvariable=self._search_var, width=30)
        self._search_entry.pack(side="left", padx=(6, 4), pady=4)
        self._search_entry.bind("<Return>",   self._do_search)
        self._search_entry.bind("<Escape>",   self._cancel_search)
        self._search_entry.bind("<FocusIn>",  self._search_focus_in)
        self._search_entry.bind("<FocusOut>", self._search_focus_out)

        self._flat_btn = ttk.Button(bar, text="Flat [V]", command=self._toggle_flat,
                                    style="TButton", width=8)
        self._flat_btn.pack(side="left", padx=4)

        self._auto_var = tk.BooleanVar(value=False)
        self._auto_chk = ttk.Checkbutton(bar, text="Auto", variable=self._auto_var,
                                          command=self._toggle_autoplay)
        self._auto_chk.pack(side="left", padx=4)

        h_paned = ttk.PanedWindow(self, orient="horizontal")
        h_paned.grid(row=1, column=0, sticky="nsew")

        tree_frame = tk.Frame(h_paned, bg=theme.PANEL, bd=0,
                              highlightthickness=2,
                              highlightbackground=theme.BORDER)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self._tree_frame = tree_frame
        h_paned.add(tree_frame, weight=0)

        self._tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse",
                                   columns=())
        self._tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.bind("<<TreeviewSelect>>", self._tree_select)
        self._tree.bind("<Double-1>", self._tree_double)
        self._tree.bind("<Up>",     lambda e: (self._tree_move_visible(-1),    "break")[1])
        self._tree.bind("<Down>",   lambda e: (self._tree_move_visible(1),     "break")[1])
        self._tree.bind("<Right>",  lambda e: (self._tree_expand_or_descend(), "break")[1])
        self._tree.bind("<Left>",   lambda e: (self._tree_go_parent(),         "break")[1])
        self._tree.bind("<Return>", lambda e: (self._tree_enter(),             "break")[1])
        self._tree.bind("<FocusIn>",  lambda _: self._set_pane_focus(self._tree_frame, True))
        self._tree.bind("<FocusOut>", lambda _: self._set_pane_focus(self._tree_frame, False))

        list_frame = tk.Frame(h_paned, bg=theme.PANEL, bd=0,
                              highlightthickness=2,
                              highlightbackground=theme.BORDER)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self._list_frame = list_frame
        h_paned.add(list_frame, weight=1)

        cols = ("name", "dur", "sr")
        self._list = ttk.Treeview(list_frame, columns=cols, show="headings",
                                   selectmode="browse")
        self._list.heading("name", text="name")
        self._list.heading("dur",  text="dur")
        self._list.heading("sr",   text="sr")
        self._list.column("name", stretch=True,  minwidth=140)
        self._list.column("dur",  width=52,  stretch=False)
        self._list.column("sr",   width=62, stretch=False)
        self._list.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(list_frame, orient="vertical", command=self._list.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self._list.configure(yscrollcommand=sb2.set)
        self._list.bind("<<TreeviewSelect>>", self._list_select)
        self._list.bind("<Double-1>", lambda _: self._play_current())
        self._list.bind("<space>", lambda e: (self._play_current(), "break")[1])
        self._list.bind("<v>", lambda _: self._toggle_flat())
        self._list.bind("<Up>",   lambda e: (self._move(-1),         "break")[1])
        self._list.bind("<Down>", lambda e: (self._move(1),          "break")[1])
        self._list.bind("<Left>", lambda e: (self._tree.focus_set(), "break")[1])
        self._list.bind("<FocusIn>",  lambda _: self._set_pane_focus(self._list_frame, True))
        self._list.bind("<FocusOut>", lambda _: self._set_pane_focus(self._list_frame, False))

    # ------------------------------------------------------------------ tree

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._tree_iid_to_path.clear()
        root = self._scanner.root
        if not root:
            return
        self._insert_tree_node("", root)
        roots = self._tree.get_children("")
        if roots:
            self._tree.selection_set(roots[0])
            self._tree.see(roots[0])

    def _insert_tree_node(self, parent_iid: str, node: DirNode) -> None:
        if not node.is_dir:
            return
        iid = self._next_iid()
        self._tree_iid_to_path[iid] = node.path
        self._tree.insert(
            parent_iid, "end", iid=iid,
            text=" " + node.name,
            open=(parent_iid == ""),
        )
        for child in node.children:
            if child.is_dir:
                self._insert_tree_node(iid, child)

    def _tree_select(self, _event: tk.Event) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        path = self._tree_iid_to_path.get(sel[0], "")
        node = self._scanner.get_node(path)
        if node:
            self._scanner.set_current_dir(node)
            self._refresh_file_list()

    def _tree_double(self, _event: tk.Event) -> None:
        pass

    # ------------------------------------------------------------------ file list

    _CHUNK = 200

    def _refresh_file_list(self) -> None:
        self._list_populate_id += 1
        my_id = self._list_populate_id
        self._list.delete(*self._list.get_children())
        self._list_iid_to_node.clear()
        nodes = list(self._scanner.file_list)
        if not nodes:
            return
        self._list_chunk(nodes, 0, my_id)

    def _list_chunk(self, nodes: list, start: int, populate_id: int) -> None:
        if populate_id != self._list_populate_id:
            return
        end = min(start + self._CHUNK, len(nodes))
        for node in nodes[start:end]:
            iid = self._next_iid()
            self._list_iid_to_node[iid] = node
            self._list.insert("", "end", iid=iid,
                               values=(node.name, "—", "—"))
        if start == 0:
            first = self._list.get_children()
            if first:
                self._list.selection_set(first[0])
                self._list_select(None)
        if end < len(nodes):
            self.after(0, lambda: self._list_chunk(nodes, end, populate_id))
        else:
            self._load_metadata_async(nodes, populate_id)

    def _load_metadata_async(self, nodes: list, populate_id: int) -> None:
        # Build a snapshot of iid→node for the background thread to match on
        iid_snapshot = {iid: n for iid, n in self._list_iid_to_node.items()}
        _BATCH = 100
        def _work() -> None:
            # Build path→iid reverse map from snapshot
            path_to_iid = {n.path: iid for iid, n in iid_snapshot.items()}
            batch: list = []
            for node in nodes:
                dur = self._fmt_dur(node.path)
                sr  = self._fmt_sr(node.path)
                if dur != "—" or sr != "—":
                    iid = path_to_iid.get(node.path)
                    if iid:
                        batch.append((iid, dur, sr))
                if len(batch) >= _BATCH:
                    b = batch[:]
                    batch.clear()
                    self.after(0, lambda b=b: self._apply_meta(b, populate_id))
            if batch:
                self.after(0, lambda b=batch: self._apply_meta(b, populate_id))
        threading.Thread(target=_work, daemon=True).start()

    def _apply_meta(self, batch: list, populate_id: int) -> None:
        if populate_id != self._list_populate_id:
            return
        for iid, dur, sr in batch:
            try:
                self._list.set(iid, "dur", dur)
                self._list.set(iid, "sr", sr)
            except Exception:
                pass

    def _list_select(self, _event) -> None:
        sel = self._list.selection()
        if not sel:
            return
        node = self._list_iid_to_node.get(sel[0])
        if node:
            self._current_node = node
            if self._on_select:
                self._on_select(node)
            if self._autoplay:
                self._engine.play(node.path)

    # ------------------------------------------------------------------ navigation helpers

    def _move(self, delta: int) -> None:
        kids = self._list.get_children()
        if not kids:
            return
        sel = self._list.selection()
        if sel:
            idx = kids.index(sel[0])
            new_idx = max(0, min(len(kids) - 1, idx + delta))
        else:
            new_idx = 0
        self._list.selection_set(kids[new_idx])
        self._list.see(kids[new_idx])
        self._list_select(None)

    def _set_pane_focus(self, frame: tk.Frame, focused: bool) -> None:
        frame.configure(
            highlightbackground=theme.SEL_FG if focused else theme.BORDER
        )

    def _tree_visible_items(self) -> list:
        result: list = []
        def collect(parent: str = "") -> None:
            for iid in self._tree.get_children(parent):
                result.append(iid)
                if self._tree.item(iid, "open"):
                    collect(iid)
        collect()
        return result

    def _tree_move_visible(self, delta: int) -> None:
        sel = self._tree.selection()
        items = self._tree_visible_items()
        if not items:
            return
        if not sel or sel[0] not in items:
            self._tree.selection_set(items[0])
            self._tree.see(items[0])
            return
        idx = items.index(sel[0])
        new_idx = max(0, min(len(items) - 1, idx + delta))
        if new_idx == idx:
            return
        self._tree.selection_set(items[new_idx])
        self._tree.see(items[new_idx])

    def _tree_expand_or_descend(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        current = sel[0]
        children = self._tree.get_children(current)
        if not children:
            self._tree_enter()
            return
        if not self._tree.item(current, "open"):
            self._tree.item(current, open=True)
        else:
            self._tree.selection_set(children[0])
            self._tree.see(children[0])

    def _tree_go_parent(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        current = sel[0]
        if self._tree.item(current, "open") and self._tree.get_children(current):
            self._tree.item(current, open=False)
            return
        parent = self._tree.parent(current)
        if parent:
            self._tree.selection_set(parent)
            self._tree.see(parent)

    def _tree_enter(self) -> None:
        kids = self._list.get_children()
        if kids:
            self._list.selection_set(kids[0])
            self._list.see(kids[0])
            self._list_select(None)
        self._list.focus_set()

    # ------------------------------------------------------------------ actions

    def _play_current(self) -> None:
        if self._current_node:
            self._engine.toggle(self._current_node.path)

    def _add_to_set(self) -> None:
        if self._current_node and self._on_add:
            self._on_add(self._current_node)

    def _quick_add(self) -> None:
        if self._current_node and self._on_quick:
            self._on_quick(self._current_node)

    def _toggle_flat(self) -> None:
        self._scanner.toggle_flat_view()
        label = "Folder [V]" if self._scanner.flat_view else "Flat [V]"
        self._flat_btn.configure(text=label)
        self._refresh_file_list()

    def _toggle_autoplay(self) -> None:
        self._autoplay = self._auto_var.get()

    def _show_search_placeholder(self) -> None:
        self._search_placeholder_active = True
        self._search_var.set("search…")
        self._search_entry.configure(style="Placeholder.TEntry")

    def _search_focus_in(self, _event=None) -> None:
        if self._search_placeholder_active:
            self._search_placeholder_active = False
            self._search_var.set("")
            self._search_entry.configure(style="TEntry")
        else:
            self._search_entry.select_range(0, "end")

    def _search_focus_out(self, _event=None) -> None:
        if not self._search_placeholder_active and not self._search_var.get().strip():
            self._show_search_placeholder()

    def _do_search(self, _event=None) -> None:
        if self._search_placeholder_active:
            return
        q = self._search_var.get().strip()
        if not q:
            self._refresh_file_list()
            return
        results = self._scanner.search(q)
        self._list_populate_id += 1
        self._list.delete(*self._list.get_children())
        self._list_iid_to_node.clear()
        for node in results:
            iid = self._next_iid()
            self._list_iid_to_node[iid] = node
            dur = self._fmt_dur(node.path)
            sr  = self._fmt_sr(node.path)
            self._list.insert("", "end", iid=iid, values=(node.name, dur, sr))
        kids = self._list.get_children()
        if kids:
            self._list.selection_set(kids[0])
            self._list.see(kids[0])
            self._list_select(None)
            self._list.focus_set()

    def _cancel_search(self, _event=None) -> None:
        self._search_placeholder_active = False
        self._search_var.set("")
        self._refresh_file_list()
        self._show_search_placeholder()
        self._list.focus_set()

    # ------------------------------------------------------------------ formatting helpers

    @staticmethod
    def _fmt_dur(path: str) -> str:
        try:
            import soundfile as sf
            info = sf.info(path)
            secs = info.frames / info.samplerate
            m, s = divmod(int(secs), 60)
            return f"{m}:{s:02d}"
        except Exception:
            return "—"

    @staticmethod
    def _fmt_sr(path: str) -> str:
        try:
            import soundfile as sf
            info = sf.info(path)
            return f"{info.samplerate // 1000}k"
        except Exception:
            return "—"

    # ------------------------------------------------------------------ public

    def set_library_root(self, path: str) -> None:
        self._tree.delete(*self._tree.get_children())
        self._list.delete(*self._list.get_children())
        self._tree_iid_to_path.clear()
        self._list_iid_to_node.clear()
        self._tree.insert("", "end", iid="__scanning__", text=" Scanning…", open=False)
        self._scanner.set_root(
            path,
            on_done=lambda: self.after(0, self._on_scan_done),
        )

    def _on_scan_done(self) -> None:
        self._refresh_tree()
        self._refresh_file_list()
        self.after_idle(self.focus_tree)

    def apply_theme(self) -> None:
        for frame in (self._tree_frame, self._list_frame):
            frame.configure(bg=theme.PANEL, highlightbackground=theme.BORDER)

    def focus_tree(self) -> None:
        self._tree.focus_set()
        if not self._tree.selection():
            roots = self._tree.get_children("")
            if roots:
                self._tree.selection_set(roots[0])
                self._tree.see(roots[0])

    def focus_search(self) -> None:
        self._search_entry.focus_set()

    def focus_list(self) -> None:
        self._list.focus_set()

    @property
    def current_node(self) -> Optional[DirNode]:
        return self._current_node
