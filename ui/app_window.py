"""
Main application window.

Assembles all panels, manages view switching (browser ↔ editor),
and routes global key bindings.

Layout:
  ┌──────────────────────────────────────────────────┐
  │  toolbar                                          │
  ├────────────────────────────────┬─────────────────┤
  │  BrowserPanel (or EditorView)  │  SetPanel        │
  ├────────────────────────────────┴─────────────────┤
  │  DetailPane                                       │
  └──────────────────────────────────────────────────┘
"""
from __future__ import annotations
import atexit
import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog
from typing import Optional

_CONFIG_PATH = Path.home() / ".kit_crafter_config.json"

from constants import VERSION, APPNAME
from core.audio_engine import AudioEngine
from core.file_scanner import FileScanner, DirNode
from core.set_manager import SetManager
from core.clip_model import ClipModel

from .browser_panel import BrowserPanel
from .set_panel import SetPanel
from .editor_view import EditorView
from .detail_pane import DetailPane
from .export_panel import ExportPanel
from .shortcuts_overlay import ShortcutsOverlay
from . import theme


class AppWindow:

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APPNAME)
        root.geometry("1100x700")
        root.minsize(800, 500)
        theme.apply(root)

        # ---- core services ----
        self._engine        = AudioEngine()
        self._scanner       = FileScanner()
        self._set_mgr       = SetManager()
        self._clip_model    = ClipModel()
        self._current_folder: str = ""

        self._build_ui()
        self._bind_global_keys()
        self._restore_state()
        self.root.after_idle(self._browser.focus_tree)

        root.protocol("WM_DELETE_WINDOW", self._on_quit)
        # macOS Cmd+Q goes through tk::mac::Quit, not WM_DELETE_WINDOW
        try:
            root.createcommand("tk::mac::Quit", self._on_quit)
        except Exception:
            pass
        # atexit catches any remaining exit path (e.g. kill signal on macOS)
        atexit.register(self._save_state)

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        # ---- toolbar ----
        toolbar = ttk.Frame(self.root, style="Panel.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(2, weight=1)

        self._title_lbl = ttk.Label(toolbar, text=APPNAME,
                  foreground=theme.SEL_FG, background=theme.PANEL,
                  font=("Menlo", 12))
        self._title_lbl.pack(side="left", padx=(12, 4), pady=6)
        self._version_lbl = ttk.Label(toolbar, text=VERSION,
                  foreground=theme.FG2, background=theme.PANEL,
                  font=("Menlo", 9))
        self._version_lbl.pack(side="left", padx=(0, 16), anchor="s", pady=(0, 7))

        self._open_btn = ttk.Button(toolbar, text="Open folder",
                                     command=self._open_folder)
        self._open_btn.pack(side="left", padx=4)

        self._path_lbl = ttk.Label(toolbar, text="no folder open",
                                    style="Muted.TLabel", background=theme.PANEL)
        self._path_lbl.pack(side="left", padx=8)

        # right side: theme name (rightmost) + playing indicator
        self._theme_lbl = ttk.Label(toolbar, text=theme.current(),
                                     style="Hint.TLabel", background=theme.PANEL)
        self._theme_lbl.pack(side="right", padx=(0, 12))

        self._play_lbl = ttk.Label(toolbar, text="",
                                    style="Green.TLabel", background=theme.PANEL)
        self._play_lbl.pack(side="right", padx=(0, 8))

        # ---- main content area (horizontal paned window for resizable split) ----
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew")

        # browser + editor share a slot; only one visible at a time
        self._main_slot = ttk.Frame(paned)
        self._main_slot.rowconfigure(0, weight=1)
        self._main_slot.columnconfigure(0, weight=1)
        paned.add(self._main_slot, weight=1)

        self._browser = BrowserPanel(
            self._main_slot,
            scanner=self._scanner,
            engine=self._engine,
            on_select=self._on_file_select,
            on_add_to_set=self._on_add,
            on_quick_add=self._on_quick_add,
        )
        self._browser.grid(row=0, column=0, sticky="nsew")

        self._editor = EditorView(
            self._main_slot,
            engine=self._engine,
            clip_model=self._clip_model,
            on_close=self._show_browser,
        )
        self._editor.grid(row=0, column=0, sticky="nsew")
        self._editor.grid_remove()

        # set panel (right) — draggable sash sets the split
        self._set_panel = SetPanel(
            paned,
            set_mgr=self._set_mgr,
            clip_model=self._clip_model,
            on_open_export=self._open_export,
            on_play=self._engine.play,
            on_select=self._on_set_select,
        )
        paned.add(self._set_panel, weight=0)

        ttk.Separator(self.root, orient="horizontal").grid(
            row=2, column=0, sticky="ew")

        # detail pane (bottom)
        self._detail = DetailPane(self.root, engine=self._engine)
        self._detail.grid(row=3, column=0, sticky="ew")

        self._in_editor = False
        self._current_node: Optional[DirNode] = None
        self._current_path: Optional[str] = None

    # ------------------------------------------------------------------ view switching

    def _show_browser(self) -> None:
        self._editor.grid_remove()
        self._browser.grid()
        self._in_editor = False
        self.root.unbind("<Escape>")
        self._browser.focus_list()

    def _show_editor(self) -> None:
        if not self._current_path:
            return
        self._browser.grid_remove()
        self._editor.grid()
        self._editor.load(self._current_path)
        self._in_editor = True
        self.root.bind("<Escape>", lambda _: self._show_browser())

    # ------------------------------------------------------------------ file events

    def _on_file_select(self, node: DirNode) -> None:
        self._current_node = node
        self._current_path = node.path
        self._detail.set_file(node.path)
        self._update_playing_label()

    def _on_set_select(self, path: str) -> None:
        self._current_path = path
        self._detail.set_file(path)

    def _on_add(self, node: DirNode) -> None:
        ok = self._set_panel.add_file(node.path, node.name.rsplit(".", 1)[0])
        if ok:
            self._flash_status(f"+ {node.name}")

    def _on_quick_add(self, node: DirNode) -> None:
        self._set_panel.show_quick_add(node.path, node.name.rsplit(".", 1)[0])

    # ------------------------------------------------------------------ toolbar

    def _open_folder(self) -> None:
        path = filedialog.askdirectory(title="Open sample library folder")
        if path:
            self._current_folder = path
            self._browser.set_library_root(path)
            self._path_lbl.configure(text=path)
            self._save_state()

    # ------------------------------------------------------------------ state persistence

    def _restore_state(self) -> None:
        try:
            data = json.loads(_CONFIG_PATH.read_text())
        except Exception:
            return

        # theme (restore before building any colours-dependent state)
        saved_theme = data.get("theme", "")
        if saved_theme:
            theme.set_theme(saved_theme, self.root)
            self._apply_theme()

        # autoplay
        if data.get("autoplay"):
            self._browser._auto_var.set(True)
            self._browser._toggle_autoplay()

        # folder
        folder = data.get("last_folder", "")
        if folder and Path(folder).is_dir():
            self._current_folder = folder
            self._browser.set_library_root(folder)
            self._path_lbl.configure(text=folder)

        # clip metadata (restore before sets so badges render correctly)
        self._clip_model._data.clear()
        for path, cd in data.get("clips", {}).items():
            active  = self._deserialize_clip(cd.get("active"))
            history = [c for c in
                       (self._deserialize_clip(x) for x in cd.get("history", []))
                       if c is not None]
            self._clip_model._data[path] = (active, history)

        # sets
        sets_data = data.get("sets", [])
        if sets_data:
            from core.set_manager import SampleSet, SetItem
            self._set_mgr._sets.clear()
            for sd in sets_data:
                s = SampleSet(id=sd["id"], name=sd["name"])
                s.items = [
                    SetItem(path=i["path"], name=i["name"], clip_id=i.get("clip_id"))
                    for i in sd.get("items", [])
                ]
                s.history = [
                    SetItem(path=i["path"], name=i["name"], clip_id=i.get("clip_id"))
                    for i in sd.get("history", [])
                ]
                self._set_mgr._sets.append(s)
            idx = data.get("active_set_index", 0)
            self._set_mgr._active_index = max(0, min(idx, len(self._set_mgr._sets) - 1))
            self._set_panel.refresh()

    def _save_state(self) -> None:
        # sets
        sets_out = []
        for s in self._set_mgr.sets:
            sets_out.append({
                "id":      s.id,
                "name":    s.name,
                "items":   [{"path": i.path, "name": i.name, "clip_id": i.clip_id}
                             for i in s.items],
                "history": [{"path": i.path, "name": i.name, "clip_id": i.clip_id}
                             for i in s.history],
            })

        # clip metadata
        clips_out: dict = {}
        for path, (active, history) in self._clip_model._data.items():
            clips_out[path] = {
                "active":  self._serialize_clip(active),
                "history": [self._serialize_clip(c) for c in history],
            }

        payload = {
            "last_folder":       self._current_folder,
            "active_set_index":  self._set_mgr._active_index,
            "sets":              sets_out,
            "clips":             clips_out,
            "theme":             theme.current(),
            "autoplay":          self._browser._auto_var.get(),
        }
        try:
            _CONFIG_PATH.write_text(json.dumps(payload, indent=2))
        except Exception:
            pass

    @staticmethod
    def _serialize_clip(clip) -> Optional[dict]:
        if clip is None:
            return None
        return {
            "start":     clip.start,
            "end":       clip.end,
            "label":     clip.label,
            "fade_in":   clip.fade.fade_in,
            "fade_out":  clip.fade.fade_out,
            "in_curve":  clip.fade.in_curve,
            "out_curve": clip.fade.out_curve,
        }

    @staticmethod
    def _deserialize_clip(d: Optional[dict]):
        if not d:
            return None
        from core.clip_model import Clip, FadeSpec
        fade = FadeSpec(
            fade_in=d.get("fade_in", 0.0),
            fade_out=d.get("fade_out", 0.0),
            in_curve=d.get("in_curve", 1.0),
            out_curve=d.get("out_curve", 1.0),
        )
        return Clip(start=d["start"], end=d["end"], fade=fade, label=d.get("label", ""))

    # ------------------------------------------------------------------ export

    def _open_export(self) -> None:
        ExportPanel(self.root, self._set_mgr, self._clip_model)

    # ------------------------------------------------------------------ global key bindings

    def _bind_global_keys(self) -> None:
        self.root.bind_all("<c>", lambda _: self._key_c())
        self.root.bind_all("<C>", lambda _: self._key_c())
        self.root.bind_all("<x>", lambda _: self._key_x())
        self.root.bind_all("<X>", lambda _: self._key_x())
        self.root.bind_all("<e>", self._key_e)
        self.root.bind_all("<E>", self._key_e)
        self.root.bind_all("<q>", self._key_q)
        self.root.bind_all("<Q>", self._key_q)
        self.root.bind_all("<f>", self._key_f)
        self.root.bind_all("<F>", self._key_f)
        self.root.bind_all("<Control-t>", lambda _: self._key_ctrl_t())
        self.root.bind_all("<Control-T>", lambda _: self._key_ctrl_t())
        self.root.bind_all("<question>", lambda _: self._key_question())
        self.root.bind_all("<space>", self._key_space, add=True)
        self.root.bind_all("<Tab>",    self._key_tab,   add=True)

    def _key_ctrl_t(self) -> None:
        new_name = theme.cycle(self.root)
        self._apply_theme()
        # self._flash_status(f"Theme: {new_name}")

    def _apply_theme(self) -> None:
        """Push updated colour values to every widget that uses direct colours."""
        for lbl in (self._title_lbl, self._version_lbl,
                    self._path_lbl, self._play_lbl, self._theme_lbl):
            lbl.configure(background=theme.PANEL)
        self._title_lbl.configure(foreground=theme.SEL_FG)
        self._version_lbl.configure(foreground=theme.FG2)
        self._theme_lbl.configure(text=theme.current())
        self._browser.apply_theme()
        self._set_panel.apply_theme()
        self._detail.apply_theme()

    def _key_e(self, event: tk.Event) -> None:
        if isinstance(event.widget, (tk.Entry, ttk.Entry)):
            return
        node = self._browser.current_node
        if not node:
            return
        if event.state & 0x1:  # Shift held
            self._on_quick_add(node)
        else:
            self._on_add(node)

    def _key_q(self, event: tk.Event) -> None:
        if isinstance(event.widget, (tk.Entry, ttk.Entry)):
            return
        self._set_panel._cycle_set()

    def _key_f(self, event: tk.Event) -> None:
        if isinstance(event.widget, (tk.Entry, ttk.Entry)):
            return
        self._browser.focus_search()

    def _key_c(self) -> None:
        if self._in_editor:
            self._show_browser()
        else:
            self._show_editor()

    def _key_x(self) -> None:
        if not self._in_editor:
            self._open_export()

    def _key_question(self) -> None:
        ShortcutsOverlay(self.root)

    def _key_space(self, event: tk.Event) -> None:
        # don't intercept space in text entries
        if isinstance(event.widget, (tk.Entry, ttk.Entry)):
            return
        if self._current_path:
            self._engine.toggle(self._current_path)
            self._update_playing_label()

    def _key_tab(self, event: tk.Event) -> None:
        if isinstance(event.widget, (tk.Entry, ttk.Entry)):
            return
        autoplay = self._browser._auto_var
        autoplay.set(not autoplay.get())
        self._browser._toggle_autoplay()
        self._flash_status("Autoplay " + ("on" if autoplay.get() else "off"))

    # ------------------------------------------------------------------ helpers

    def _update_playing_label(self) -> None:
        if self._engine.is_playing():
            path = self._engine.current or ""
            import os
            self._play_lbl.configure(text="▶ " + os.path.basename(path))
        else:
            self._play_lbl.configure(text="")
        self.root.after(500, self._update_playing_label)

    def _flash_status(self, msg: str) -> None:
        self._play_lbl.configure(text=msg, foreground=theme.GREEN)
        self.root.after(1500, lambda: self._play_lbl.configure(foreground=theme.GREEN))

    # ------------------------------------------------------------------ quit

    def _on_quit(self) -> None:
        self._save_state()
        self._engine.cleanup()
        self.root.destroy()
