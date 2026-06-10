# Kit Crafter — Recreation Prompt

Build a keyboard-first desktop audio sample browser called **Kit Crafter** in Python/tkinter. Single window, no web backend. Python 3.10+.

Run: `python main.py [optional_folder]`  
Config persisted: `~/.kit_crafter_config.json`

---

## File structure

```
constants.py        VERSION="v0.95"  APPNAME="Kit Crafter"
requirements.txt    pygame-ce>=2.5 soundfile>=0.12 numpy>=1.24 pydub>=0.25
main.py
core/__init__.py
core/audio_engine.py
core/file_scanner.py
core/clip_model.py
core/set_manager.py
core/exporter.py
ui/__init__.py
ui/theme.py
ui/waveform_view.py
ui/editor_view.py
ui/browser_panel.py
ui/set_panel.py
ui/detail_pane.py
ui/export_panel.py
ui/shortcuts_overlay.py
ui/app_window.py
```

---

## main.py

```python
import sys, os, tkinter as tk
sys.path.insert(0, os.path.dirname(__file__))
from ui.app_window import AppWindow
root = tk.Tk()
app = AppWindow(root)
if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    app._browser.set_library_root(sys.argv[1])
    app._path_lbl.configure(text=sys.argv[1])
root.mainloop()
```

---

## core/audio_engine.py

Guard pygame with:
```python
try:
    import pygame, pygame.mixer
    _PYGAME = True
except (ImportError, NotImplementedError):
    _PYGAME = False
```

`AUDIO_EXTS = {".wav",".aif",".aiff",".flac",".mp3",".ogg",".opus"}`

`AudioEngine.__init__`: if `_PYGAME`: `pygame.mixer.init(44100,-16,2,1024)`

Methods:
- `play(path)->bool`: `mixer.music.load(path); mixer.music.play(); self._current=path`
- `stop()`: `mixer.music.stop()`
- `toggle(path=None)`: stop if busy, else play path or `self._current`
- `is_playing()->bool`: `_PYGAME and bool(mixer.music.get_busy())`
- `current` property
- `get_position()->Optional[float]`: `pos=mixer.music.get_pos(); return pos/1000 if pos>=0 else None`
- `load_waveform(path, n_points=2000)->Optional[np.ndarray]`: soundfile read→mono float32→downsample→cache by path
- `load_waveform_async(path, callback)`: daemon thread calling `load_waveform`, then `callback(result)` — caller marshals to main thread via `.after(0,...)`
- `file_info(path)->dict`: `sf.info` → `{sr, channels, frames, duration=frames/sr, subtype}`; empty dict on error
- `clear_cache()`, `cleanup()`: `mixer.quit()`

---

## core/file_scanner.py

```python
@dataclass
class DirNode:
    path:str; name:str; is_dir:bool
    children:List["DirNode"] = field(default_factory=list)
    parent:Optional["DirNode"] = field(default=None, repr=False)
```

`FileScanner`:
- `set_root(path, on_done=None)`: background thread; `_scan_id` counter discards stale results; builds full `DirNode` tree (dirs first, alpha, skip dotfiles); `on_done()` called on bg thread — caller schedules to main thread
- `get_node(path)->Optional[DirNode]`: O(1) via `_node_by_path` dict
- `toggle_flat_view()`, `set_current_dir(node)`, `navigate_up()`
- `file_list` property: flat audio files if `_flat_view` else direct audio children of `current_dir`
- `dir_children` property
- `search(query)->List[DirNode]`: case-insensitive recursive from root, returns audio nodes matching name

---

## core/clip_model.py

```python
@dataclass
class FadeSpec:
    fade_in:float=0.0; fade_out:float=0.0
    in_curve:float=1.0; out_curve:float=1.0

@dataclass
class Clip:
    start:float; end:float
    fade:FadeSpec=field(default_factory=FadeSpec); label:str=""
    @property
    def duration(self): return max(0.0, self.end-self.start)
    def is_valid(self): return self.end>self.start and self.start>=0
```

`ClipModel._data: Dict[str, (Optional[Clip], List[Clip])]`
- `get_clip(path)`, `get_history(path)`, `has_clip(path)`
- `set_clip(path,start,end,fade)`: pushes previous active to front of history
- `clear_clip(path)`: moves active to history, sets None
- `restore_from_history(path,index)`: swaps history[index] to active
- `all_paths_with_clips()`: paths with valid active clip

---

## core/set_manager.py

```python
@dataclass
class SetItem:
    path:str; name:str; clip_id:Optional[str]=None

@dataclass
class SampleSet:
    id:str=field(default_factory=lambda:str(uuid.uuid4())[:8])
    name:str="New set"
    items:List[SetItem]=field(default_factory=list)
    history:List[SetItem]=field(default_factory=list)
    def add(self,path,name)->bool   # False if duplicate
    def remove(self,path)           # prepend to history
    def restore(self,path)          # move from history back to items
    def contains(self,path)->bool
    def rename_item(self,path,new_name)
```

`SetManager`: starts with `SampleSet(name="Set 1")`.
- `new_set(name)`, `remove_set(set_id)` (refuses if last), `rename_set(set_id,name)`
- `active` property, `cycle_active()`, `set_active(set_id)`
- `add_to_active(path,name)`, `add_to_set(set_id,path,name)`, `remove_from_active(path)`
- `sets` property (copy), `get(set_id)`

---

## core/exporter.py

```python
@dataclass
class ExportSettings:
    output_dir:str=""; fmt:str="WAV"; subtype:str="PCM_16"
    target_sr:int=44100; mono:bool=True; normalize:bool=True
    normalize_db:float=-0.1; hpf:bool=False; hpf_freq:float=40.0; limiter:bool=False
```

`BUILTIN_PRESETS`:
- TR-8S: WAV/PCM_16/44.1k/mono/normalize
- Octatrack: WAV/PCM_16/44.1k/stereo/normalize
- SP-404 MK2: WAV/PCM_16/44.1k/stereo/normalize
- DAW (24-bit): WAV/PCM_24/48k/stereo/no-normalize

`export_file(src,out_dir,out_name,settings,clip)->Tuple[bool,str]` chain:
1. `sf.read(float32, always_2d=True)`
2. Slice clip frames; apply fades via `np.linspace**curve` envelope
3. Mono: `data.mean(axis=1)`
4. Resample: librosa if available, else `np.interp` linear fallback
5. HPF: first-order IIR — `alpha=rc/(rc+dt)`; loop over frames
6. Normalize: `data*(10**(db/20))/peak`
7. `sf.write(path, data, sr, subtype=subtype)`

`BatchExporter(items,out_dir,settings,on_progress,on_done)`: daemon thread, calls `export_file` sequentially, fires `on_progress(done,total,msg)` and `on_done(ok,total)`. Has `cancel()` flag.

---

## ui/theme.py

Module-level globals: `BG PANEL SURFACE BORDER SEL SEL_FG FG FG2 FG3 GREEN ORANGE RED HOVER PRESSED SEL_HOVER`  
Fonts: `FONT=("Menlo",11)  FONT_S=("Menlo",10)  FONT_XS=("Menlo",9)`

Four palettes in `_PALETTES` dict:
- **Classic**: grays (`BG=#1a1a1a`), blue sel (`SEL=#1e3a5f SEL_FG=#5aadff`)
- **Amethyst**: purple-black (`BG=#0d0c10`), violet (`SEL=#2a1f4e SEL_FG=#a78bfa`)
- **Neon**: near-black purple (`BG=#090812`), hot pink (`SEL=#200a3e SEL_FG=#f72585`)
- **Midnight**: navy (`BG=#0b0f1c`), cyan (`SEL=#1a2e4a SEL_FG=#58b8f8`), teal green (`#3ddbb8`), blue text (`FG=#c6d8ee`)

`apply(root)`: `style.theme_use("clam")` then configure all styles:
`TFrame Panel.TFrame Surface.TFrame TLabel Muted.TLabel Hint.TLabel Accent.TLabel Green.TLabel TButton Accent.TButton TEntry Placeholder.TEntry TScrollbar Treeview Treeview.Heading TSeparator TCheckbutton TCombobox TLabelframe`

`cycle(root)->str`: advance palette, reload globals, re-apply.  
`set_theme(name,root)`: set by name.  
`kbd_label(parent,text)->tk.Label`: small badge, `bg=SURFACE fg=FG2 font=FONT_XS padx=3 pady=1`

---

## ui/waveform_view.py — `WaveformCanvas(tk.Canvas)`

Constants: `CLIP_COLOR="#5aadff" CLIP_FILL="#1e3a5f" WAVE_COLOR="#888888" WAVE_SEL_COLOR="#aaaaaa" PLAY_COLOR="#4aff88" FADE_COLOR="#ffaa44"`

State: `_data _sr _duration _clip_start _clip_end _fade_in_len _fade_out_len _view_start=0 _view_end=1 _playhead`  
Callback: `on_clip_change(start_s,end_s,fade_in_s,fade_out_s)`

API:
- `set_waveform(data,sr=44100,duration=None)`: use `duration` if given, else `len(data)/sr`
- `set_clip(start_s,end_s,fade_in_s=0,fade_out_s=0)`: normalise to [0..1]
- `clear_clip()`
- `set_playhead(pos_s)`: **guard `pos_s is not None`** (not truthiness — 0.0 is valid); normalise as `pos_s/duration`

Drawing (`_redraw`): editor mode → top 65% `_draw_wave_region`, bottom 35% `_draw_overview`; mini mode → full height `_draw_wave_region`.

`_draw_wave_region(x0,y0,w,h)`:
1. Clip fill rect + vertical boundary lines
2. Fade-in overlay: stipple rect + dashed diagonal `FADE_COLOR`
3. Fade-out overlay: same
4. Waveform bars: per-pixel column, `WAVE_SEL_COLOR` inside clip else `WAVE_COLOR`
5. Playhead: `PLAY_COLOR` vertical line

`_draw_overview(x0,y0,w,h)`: mini waveform in `FG3` + viewport highlight rect

Editor-mode mouse: `ButtonPress-1 B1-Motion ButtonRelease-1` in top 65% → drag updates `_clip_start/_clip_end`; release fires `on_clip_change`.

---

## ui/editor_view.py — `EditorView(ttk.Frame)`

Constructor args: `parent, engine, clip_model, on_close`

Layout (grid):
- Row 0: header bar — filename label (`Accent.TLabel`) + "Esc / close" button
- Row 1 (weight=1): `WaveformCanvas(editor_mode=True, height=280)`
- Row 2: fade controls — two `ttk.Scale(0–2s)` with numeric labels
- Row 3: clip info `StringVar` left; "▶ Preview" "Clear clip" "Save clip" buttons right; history count label

`load(path)`:
1. Store path, update title
2. `engine.load_waveform_async` → in callback: `engine.file_info(path)` for `duration`/`sr`, call `wave.set_waveform(data,sr,duration)`; all marshalled via `.after(0,...)`
3. Restore clip from `clip_model` if valid → set sliders + `wave.set_clip`
4. Update history count
5. Start `_tick_playhead` if `not self._tracking`

`_tick_playhead` (40ms loop ≈25fps): if `engine.is_playing() and engine.current==self._path` → `wave.set_playhead(engine.get_position())` else `wave.set_playhead(None)`. Stop when `_tracking=False`.

On clip drag: update `_start_s/_end_s`, call `wave.set_clip` with current fade slider values (do not override sliders).  
Save clip: `clip_model.set_clip(path,start,end,FadeSpec(...))`.  
Close: `_tracking=False`, `wave.set_playhead(None)`, call `on_close`.

---

## ui/browser_panel.py — `BrowserPanel(ttk.Frame)`

Constructor args: `parent, scanner, engine, on_select, on_add_to_set, on_quick_add`

Layout:
- Top bar: search `ttk.Entry` (placeholder "search…" styled `Placeholder.TEntry`), "Flat [V]" button, "Auto" checkbutton
- Inner `ttk.PanedWindow(horizontal)`:
  - Left: folder tree `ttk.Treeview(show="tree")` in a `tk.Frame(highlightthickness=2)` for focus border
  - Right: file list `ttk.Treeview(show="headings", columns=name/dur/sr)` same border frame

**Critical**: use numeric string IIDs (not paths) — maintain `_tree_iid_to_path` and `_list_iid_to_node` dicts.

Tree keys: `↑↓` move visible items; `→` expand or descend; `←` collapse or go to parent; `Enter` jump to file list. Focus border: `BORDER` unfocused, `SEL_FG` focused.

File list population: chunks of 200 via `after(0,...)`. Metadata (dur/sr via soundfile) loaded in bg thread batches of 100, applied via `after(0,...)`. On select: fire `on_select(node)`; autoplay if enabled. `V` toggles flat view; `←` returns focus to tree. Double-click / Space plays.

Search: `Enter` → `scanner.search(q)` → populate list. `Escape` → clear + restore normal list. Placeholder restored on focus-out when empty.

Public: `set_library_root(path)` (show "Scanning…", call `scanner.set_root`, refresh on done), `apply_theme()`, `focus_tree()`, `focus_search()`, `focus_list()`, `current_node` property.

---

## ui/set_panel.py — `SetPanel(ttk.Frame)`

Constructor args: `parent, set_mgr, clip_model, on_open_export, on_play, on_select`

Layout (top→bottom):
- Header: "ACTIVE SET" muted label + "N" (new set) + "Q" (cycle) buttons
- Tab strip (`_tabs_frame`): one `tk.Button` per set; active: `bg=SEL fg=SEL_FG`; others: `bg=SURFACE fg=FG2`
- `tk.Listbox`: each item = `name + " ✂"` if `clip_model.has_clip(item.path)`
- History row: "history" hint label + "▾" button → popup listbox of removed items, double-click restores
- "Export set [X]" `Accent.TButton`

Events: `<<ListboxSelect>>` → `on_select(item.path)`; double-click → `on_play(path)`; Delete/Backspace → `remove_from_active`.

Public: `add_file(path,name)->bool`, `add_file_to(set_id,path,name)->bool`, `show_quick_add(path,name)` (Toplevel with set listbox, double-click adds), `refresh()`, `apply_theme()` (re-builds tabs + reconfigures listbox colours).

---

## ui/detail_pane.py — `DetailPane(ttk.Frame)`

Two-column grid:
- Col 0: filename (`Accent.TLabel`); fields row: `sr ch dur bpm key` each as hint+muted pair; tags row: "tags:" + Entry + "save" button
- Col 1: shortcut hints as `kbd_label` + hint label pairs: `F search / Space play-stop / E add-to-set / C editor / X export / Ctrl+T theme`

`set_file(path)`: call `engine.file_info`, populate sr/ch/dur; clear bpm/key.  
`set_bpm_key(bpm,key)`.  
`apply_theme()`: update `kbd_label` bg/fg.

---

## ui/export_panel.py — `ExportPanel(tk.Toplevel)` 460×440

- Header label
- Preset strip: `tk.Button` per `BUILTIN_PRESETS` — clicking applies all settings vars
- Separator
- Settings grid rows: Mono(check), Normalize(check), Peak dBFS(entry), High-pass(check), HPF freq(entry), Limiter(check), Format(combobox WAV/AIFF/FLAC), Bit depth(combobox PCM_16/24/32), Sample rate(combobox 22050/44100/48000/96000)
- Output folder: Entry + "…" browse button
- `ttk.Progressbar` + status `StringVar` label
- "Export set" `Accent.TButton` → builds `ExportSettings`, creates `BatchExporter`, starts it; progress/done callbacks via `after(0,...)`; `messagebox.showinfo` on done

---

## ui/shortcuts_overlay.py — `ShortcutsOverlay(tk.Toplevel)` 460×480

`SHORTCUTS` list of `(section, [(key,desc)])`:
- Navigation: ↑↓ →  ← Enter F V Esc
- Playback: Space Tab
- Set management: E Shift+E N Q Delete
- Panels: C X Ctrl+T ? Esc

Two-column layout (even sections left, odd right). Each row: `kbd_label` + muted hint. Escape closes.

---

## ui/app_window.py — `AppWindow`

`__init__`: create `AudioEngine FileScanner SetManager ClipModel`, call `theme.apply(root)`, build UI, bind keys, `_restore_state()`, `root.after_idle(_browser.focus_tree)`. Wire `WM_DELETE_WINDOW` and `tk::mac::Quit` to `_on_quit`. `atexit.register(_save_state)`.

**Layout**: `root` grid row 0=toolbar, row 1=`ttk.PanedWindow(horizontal)`, row 2=separator, row 3=DetailPane.

PanedWindow left: `_main_slot` frame holds browser (weight=1 grid) and editor (weight=1 grid) stacked at row 0 col 0; only one visible. Right: SetPanel (weight=0).

**View switching**:
- `_show_browser()`: `editor.grid_remove()`, `browser.grid()`, `_in_editor=False`, unbind Escape, `_browser.focus_list()`
- `_show_editor()`: guard `_current_path`; `browser.grid_remove()`, `editor.grid()`, `editor.load(_current_path)`, `_in_editor=True`, bind Escape→`_show_browser`

**Global bindings** (`bind_all`) — skip when focus is `tk.Entry` or `ttk.Entry`:
- `c/C`: toggle editor
- `e/E`: add to active set (Shift = quick-add via `event.state & 0x1`)
- `q/Q`: cycle set
- `f/F`: focus search
- `x/X`: open export (only when not in editor)
- `Ctrl+T`: `theme.cycle(root)`, `_apply_theme()`
- `?`: `ShortcutsOverlay(root)`
- `Space`: `engine.toggle(_current_path)` + update playing label
- `Tab`: toggle autoplay

`_apply_theme()`: update toolbar label colours/backgrounds + call `browser.apply_theme()  set_panel.apply_theme()  detail.apply_theme()`.

**Playing label poll** (500ms `after` loop): shows `"▶ filename"` when `engine.is_playing()`.

**State persistence** (`~/.kit_crafter_config.json`):  
Save: `last_folder, active_set_index, sets[]{id,name,items[]{path,name,clip_id},history[]}, clips{path:{active:{start,end,label,fade_in,fade_out,in_curve,out_curve},history:[]}}, theme, autoplay`  
Restore: theme first (then `_apply_theme()`), autoplay, folder, clips, sets. Restore clips before sets so `✂` badges render correctly.

---

## Key constraints

1. **No audio on main thread** — all waveform loading and metadata reads in daemon threads, results via `.after(0,callback)`
2. **Playhead guard**: `set_playhead` must check `pos_s is not None` not `if pos_s` — 0.0 is valid
3. **Treeview IIDs must be numeric strings** — never use file paths as IIDs
4. **Chunked list fill**: 200 items per `after(0,...)` tick
5. **Clip duration from file_info** — pass actual `duration` from `engine.file_info(path)["duration"]` to `wave.set_waveform`, not computed from downsampled array
6. **pygame-ce** (not pygame) — installs with working `pygame.mixer` on macOS
