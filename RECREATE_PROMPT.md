Build a keyboard-first desktop audio sample browser and manager called **Kit Crafter** in Python using tkinter. It runs as a single-window app with no web backend. Target Python 3.10+.

---

## Dependencies

```
pygame>=2.5
soundfile>=0.12
numpy>=1.24
pydub>=0.25
```

Optional (for resampling quality): `librosa`. Fall back to numpy linear interpolation when absent.

---

## Project structure

```
main.py
constants.py          # VERSION = "v0.95", APPNAME = "Kit Crafter"
requirements.txt
core/
  __init__.py
  audio_engine.py
  file_scanner.py
  clip_model.py
  set_manager.py
  exporter.py
ui/
  __init__.py
  theme.py
  app_window.py
  browser_panel.py
  set_panel.py
  editor_view.py
  waveform_view.py
  detail_pane.py
  export_panel.py
  shortcuts_overlay.py
```

---

## Window layout

```
┌─────────────────────────────────────────────────────────┐
│  toolbar (app name + version + Open Folder + path label) │
├──────────────────────────────────┬──────────────────────┤
│  BrowserPanel  ←→  EditorView    │  SetPanel            │
│  (one visible at a time,         │  (always visible,    │
│   left side of horizontal pane)  │   right side)        │
├──────────────────────────────────┴──────────────────────┤
│  DetailPane (bottom strip, always visible)               │
└─────────────────────────────────────────────────────────┘
```

The center+right area is a `ttk.PanedWindow` (horizontal, draggable sash). The left slot (`_main_slot`) holds both BrowserPanel and EditorView stacked in grid row 0; only one is visible at a time via `grid()` / `grid_remove()`.

---

## Theme system (`ui/theme.py`)

Define module-level color variables (`BG`, `PANEL`, `SURFACE`, `BORDER`, `SEL`, `SEL_FG`, `FG`, `FG2`, `FG3`, `GREEN`, `ORANGE`, `RED`, `HOVER`, `PRESSED`, `SEL_HOVER`) and fonts (`FONT = ("Menlo", 11)`, `FONT_S`, `FONT_XS`).

Four named palettes in a `_PALETTES` dict:

- **Classic**: neutral dark grays, blue selection (`#1e3a5f` / `#5aadff`)
- **Amethyst**: deep purple-black, violet selection (`#2a1f4e` / `#a78bfa`)
- **Neon**: near-black purple, hot pink selection (`#200a3e` / `#f72585`)
- **Midnight**: deep navy blue-black (`#0b0f1c`), cyan-blue selection (`#1a2e4a` / `#58b8f8`), blue-tinted text (`#c6d8ee`), teal green (`#3ddbb8`)

`apply(root)` configures the `clam` ttk theme with all styles: `TFrame`, `Panel.TFrame`, `Surface.TFrame`, `TLabel`, `Muted.TLabel`, `Hint.TLabel`, `Accent.TLabel`, `Green.TLabel`, `TButton`, `Accent.TButton`, `TEntry`, `Placeholder.TEntry`, `TScrollbar`, `Treeview`, `Treeview.Heading`, `TSeparator`, `TCheckbutton`, `TCombobox`, `TLabelframe`.

`cycle(root)` advances to the next palette and re-applies. `set_theme(name, root)` switches by name. Provide `kbd_label(parent, text)` that returns a small `tk.Label` styled as a keyboard badge.

---

## Core: `AudioEngine`

Uses `pygame.mixer` for playback (init at 44100 Hz, 16-bit, 2ch, buffer 1024). Guard all pygame calls with an `_PYGAME` flag in case import fails.

- `play(path) -> bool` — loads and plays a file, sets `self._current`
- `stop()`, `toggle(path=None)`
- `is_playing() -> bool` — wraps `pygame.mixer.music.get_busy()`
- `current: str` — property, path of last played file
- `get_position() -> Optional[float]` — returns `pygame.mixer.music.get_pos() / 1000.0` (seconds); returns `None` if `get_pos()` < 0
- `load_waveform(path, n_points=2000) -> Optional[np.ndarray]` — reads with soundfile, converts to mono float32, downsamples to at most `n_points` samples, caches by path
- `load_waveform_async(path, callback)` — runs `load_waveform` in a daemon thread, calls `callback(data)` from that thread (caller must marshal to main thread via `.after(0, ...)`)
- `file_info(path) -> dict` — returns `{sr, channels, frames, duration, subtype}` via `sf.info`; empty dict on error
- `clear_cache()`, `cleanup()` (calls `pygame.mixer.quit()`)
- `AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".opus"}`

---

## Core: `FileScanner`

Represents the library folder tree. Supports folder-tree view (immediate children of `current_dir`) and flat view (all audio files recursively under `current_dir`).

`DirNode` dataclass: `path`, `name`, `is_dir`, `children: List[DirNode]`, `parent: Optional[DirNode]`.

- `set_root(path, on_done=None)` — scans in a background daemon thread; uses a `_scan_id` counter to discard stale results; builds the full `DirNode` tree recursively, sorts entries with dirs first then alphabetically, skips dotfiles; calls `on_done()` when complete
- `get_node(path) -> Optional[DirNode]` — O(1) lookup via `_node_by_path` dict
- `toggle_flat_view()` — flips `_flat_view` and refreshes `_file_list`
- `set_current_dir(node)`, `navigate_up()`
- `file_list` property — audio files visible in current context
- `dir_children` property — subdirs of `current_dir`
- `search(query) -> List[DirNode]` — case-insensitive recursive search from root, returns audio file nodes whose names contain the query
- Audio extensions: same set as `AudioEngine.AUDIO_EXTS`

---

## Core: `ClipModel`

Pure metadata; no audio is touched.

`FadeSpec` dataclass: `fade_in: float`, `fade_out: float`, `in_curve: float = 1.0`, `out_curve: float = 1.0`.

`Clip` dataclass: `start: float`, `end: float`, `fade: FadeSpec`, `label: str`. Properties: `duration`, `is_valid()` (end > start >= 0).

`ClipModel` stores `_data: Dict[str, (Optional[Clip], List[Clip])]` (active clip + history per path).

- `get_clip(path)`, `get_history(path)`, `has_clip(path)`
- `set_clip(path, start, end, fade)` — pushes previous active clip to front of history
- `clear_clip(path)` — moves active to history, sets active to None
- `restore_from_history(path, index)` — swaps history[index] to active
- `all_paths_with_clips()` — returns paths that have a valid active clip

---

## Core: `SetManager`

`SetItem` dataclass: `path`, `name`, `clip_id: Optional[str]`.

`SampleSet` dataclass: `id` (8-char uuid), `name`, `items: List[SetItem]`, `history: List[SetItem]`.
Methods: `add(path, name) -> bool` (False if already present), `remove(path)` (moves to front of history), `restore(path)`, `contains(path)`, `rename_item(path, new_name)`.

`SetManager`:
- Starts with one default set named "Set 1"
- `new_set(name)` — appends and makes active
- `remove_set(set_id)` — refuses if only one set remains
- `rename_set(set_id, name)`
- `active` property, `cycle_active()`, `set_active(set_id)`
- `add_to_active(path, name)`, `add_to_set(set_id, path, name)`, `remove_from_active(path)`
- `sets` property (copy of list), `get(set_id)`

---

## Core: `Exporter`

`ExportSettings` dataclass: `output_dir`, `fmt` (WAV/AIFF/FLAC), `subtype` (PCM_16/PCM_24/PCM_32), `target_sr`, `mono: bool`, `normalize: bool`, `normalize_db: float = -0.1`, `hpf: bool`, `hpf_freq: float = 40.0`, `limiter: bool`.

`ExportPreset`: `name`, `settings`. Built-in presets: TR-8S (WAV 16-bit 44.1k mono normalize), Octatrack (WAV 16-bit 44.1k stereo normalize), SP-404 MK2 (WAV 16-bit 44.1k stereo normalize), DAW 24-bit (WAV 24-bit 48k stereo no-normalize).

`export_file(src_path, out_dir, out_name, settings, clip)` processing chain (all in-memory with numpy):
1. Read float32 with soundfile (always_2d=True)
2. Apply clip region (slice frames)
3. Apply fades using `np.linspace` raised to `in_curve`/`out_curve` exponent
4. Convert to mono (`data.mean(axis=1)`) if `settings.mono`
5. Resample via librosa if available, else numpy linear interpolation
6. First-order IIR high-pass filter if `settings.hpf`
7. Peak-normalize to `normalize_db` dBFS ceiling if `settings.normalize`
8. Write with soundfile using correct subtype and format

`BatchExporter` — takes `items: List[(path, name, clip)]`, runs `export_file` sequentially in a daemon thread, fires `on_progress(done, total, msg)` and `on_done(ok, total)` callbacks.

---

## UI: `WaveformCanvas`

A `tk.Canvas` subclass used in both mini mode (detail pane) and editor mode (full waveform editor).

**State:**
- `_data: Optional[np.ndarray]` — downsampled waveform (mono float32 [-1..1])
- `_sr: int`, `_duration: float` — **set from the actual file duration passed in, not computed from downsampled array length**
- `_clip_start`, `_clip_end`: Optional[float] — normalised [0..1] coords
- `_fade_in_len`, `_fade_out_len`: float — normalised fraction of clip width
- `_view_start`, `_view_end`: float — zoom/pan state for overview strip (normalised)
- `_playhead: Optional[float]` — normalised [0..1]

**API:**
- `set_waveform(data, sr=44100, duration=None)` — if `duration` is provided use it directly; otherwise derive from `len(data)/sr`. Store and redraw.
- `set_clip(start_s, end_s, fade_in_s=0.0, fade_out_s=0.0)` — converts to normalised coords and redraws
- `clear_clip()`
- `set_playhead(pos_s: Optional[float])` — normalises as `pos_s / duration` **only when `pos_s is not None and duration > 0`** (do not use truthiness check — pos_s can be 0.0)
- `on_clip_change` callback: `(start_s, end_s, fade_in_s, fade_out_s)`

**Drawing (`_redraw`):**
In editor mode: top 65% is `_draw_wave_region`, bottom 35% is `_draw_overview`. In mini mode: full height is `_draw_wave_region`.

`_draw_wave_region(x0, y0, w, h)`:
1. Clip fill rectangle (`CLIP_FILL = "#1e3a5f"`) with vertical boundary lines (`CLIP_COLOR = "#5aadff"`)
2. Fade-in overlay: filled rect + diagonal dashed line from bottom-left to top-right (`FADE_COLOR = "#ffaa44"`)
3. Fade-out overlay: filled rect + diagonal dashed line
4. Waveform bars: for each pixel column, find the sample amplitude, draw a vertical line centred on mid-y; use `WAVE_SEL_COLOR = "#aaaaaa"` inside clip, `WAVE_COLOR = "#888888"` outside
5. Playhead: bright green vertical line (`PLAY_COLOR = "#4aff88"`)

`_draw_overview(x0, y0, w, h)`: draws a miniature version of the full waveform, plus a viewport highlight rectangle showing the current `_view_start`/`_view_end` range.

**Interaction (editor mode only):** bind `ButtonPress-1`, `B1-Motion`, `ButtonRelease-1`. Top 65% of canvas height is the clip-drag zone; bottom 35% is reserved for future zoom/pan. On drag, update `_clip_start`/`_clip_end` from mouse x. On release, fire `on_clip_change`.

---

## UI: `EditorView`

A `ttk.Frame` shown in the `_main_slot` when the user opens the waveform editor. Contains:

- **Header bar**: filename label + "Esc / close" button
- **WaveformCanvas** in editor mode, height 280 px — takes `weight=1` row
- **Fade controls**: two `ttk.Scale` sliders (0–2 s each) with numeric labels for fade-in and fade-out
- **Clip info + actions bar**: clip info StringVar label on left; "▶ Preview", "Clear clip", "Save clip" buttons on right; history count label
- `on_clip_change` wired to an internal callback that updates start/end state and refreshes the waveform (does not override fade sliders from drag)

**Loading** (`load(path)`):
1. Store path, update title
2. Call `engine.load_waveform_async` — in callback, call `engine.file_info` to get actual `duration` and `sr`, pass `duration` to `wave.set_waveform`
3. Restore existing clip from `ClipModel` if present (set sliders, call `wave.set_clip`)
4. Update history count label
5. Start playhead tracking loop if not already running (`_tracking` flag)

**Playhead tracking loop** (`_tick_playhead`, ~25 fps via `after(40, ...)`):
Check `engine.is_playing() and engine.current == self._path`; if true, call `wave.set_playhead(engine.get_position())`; else call `wave.set_playhead(None)`. Stop when `_tracking` is False (set in `_close()`).

**Save clip** — calls `clip_model.set_clip` with current start/end and fade values. **Preview** — calls `engine.play(path)`. **Close** — sets `_tracking = False`, calls `wave.set_playhead(None)`, fires `on_close` callback.

---

## UI: `BrowserPanel`

A `ttk.Frame` split horizontally (inner `PanedWindow`) into a folder tree (left, `weight=0`) and a file list (right, `weight=1`).

**Top bar**: search entry with placeholder text "search…" (styled `Placeholder.TEntry` when inactive), "Flat [V]" toggle button, "Auto" checkbutton.

**Folder tree** (`ttk.Treeview`, `show="tree"`):
- Populated from `FileScanner` tree; only directory nodes inserted
- Use numeric IIDs (not paths) to avoid Tcl special-character issues; maintain `_tree_iid_to_path` dict
- Root node starts open; selecting a node calls `scanner.set_current_dir` and refreshes file list
- Keys: ↑/↓ move through all visible (expanded) items; → expands if collapsed, else enters first child; ← collapses if open, else selects parent; Enter jumps to file list
- Focus border: `highlightthickness=2`, switches between `theme.BORDER` (unfocused) and `theme.SEL_FG` (focused)

**File list** (`ttk.Treeview`, `show="headings"`, columns: name / dur / sr):
- Populated in chunks of 200 via `after(0, ...)` to keep UI responsive
- Metadata (duration, sample rate via soundfile) loaded in background thread in batches of 100, marshalled back to main thread via `after(0, ...)`
- Selecting a row fires `on_select(node)` callback; double-click or Space plays the file
- V key toggles flat/folder view; Left arrow returns focus to tree
- Autoplay: plays file automatically on selection when enabled

**Search**: Enter runs search (calls `scanner.search`), populates list with results. Escape clears and restores normal file list. Placeholder is restored on focus-out when entry is empty.

**Public API**: `set_library_root(path)` — shows "Scanning…" placeholder, calls `scanner.set_root`, refreshes on done. `apply_theme()`, `focus_tree()`, `focus_search()`, `focus_list()`, `current_node` property.

---

## UI: `SetPanel`

A `ttk.Frame` on the right side. Shows the active set's contents.

**Layout (top to bottom):**
- Header: "ACTIVE SET" label, "N" (new set) button, "Q" (cycle set) button
- Tab strip: one `tk.Button` per set; active set highlighted with `theme.SEL` background, others `theme.SURFACE`
- Item listbox (`tk.Listbox`): each item shows `name` + ` ✂` badge if a clip exists in `ClipModel`
- History row: "history" label + "▾" button that opens a popup to restore removed items
- Export button: "Export set [X]"

**Interactions:**
- `<<ListboxSelect>>` fires `on_select(item.path)` callback (for detail pane and editor access)
- Double-click plays the item via `on_play`
- Delete / Backspace removes selected item (moves to history)
- History popup: lists removed items; double-click restores to active set

**Public API:** `add_file(path, name) -> bool`, `add_file_to(set_id, path, name) -> bool`, `show_quick_add(path, name)` (popup with listbox of all sets), `refresh()`, `apply_theme()`.

Constructor params: `set_mgr`, `clip_model`, `on_open_export`, `on_play`, `on_select`.

---

## UI: `DetailPane`

A `ttk.Frame` at the bottom. Two columns: info on left, keyboard shortcut hints on right.

**Left column:**
- Filename label (Accent style)
- Technical fields row: `sr`, `ch`, `dur`, `bpm`, `key` — each a hint label + muted value label
- Tags row: "tags:" label + entry field + "save" button (comma-separated; saved to instance list but not persisted)

**Right column:** keyboard shortcut hint pairs (F=search, Space=play/stop, E=add to set, C=editor, X=export, Ctrl+T=switch theme) — each a kbd_label badge + hint label.

`set_file(path)` — calls `engine.file_info`, populates sr/ch/dur labels; clears bpm/key. `set_bpm_key(bpm, key)` for optional analysis results. `apply_theme()` updates kbd_label backgrounds.

---

## UI: `ExportPanel`

A modal `tk.Toplevel` (460×440). Opened by pressing X.

**Layout:**
- "Export settings" header
- Preset strip: buttons for each built-in preset; clicking applies all settings
- Separator
- Settings grid: Mono (checkbox), Normalize (checkbox), Peak dBFS (entry), High-pass (checkbox), HPF freq (entry), Limiter (checkbox), Format (combobox: WAV/AIFF/FLAC), Bit depth (combobox: PCM_16/PCM_24/PCM_32), Sample rate (combobox: 22050/44100/48000/96000)
- Output folder row: entry + "…" browse button
- Progress bar + status label
- "Export set" accent button

Starts `BatchExporter` on click; updates progress bar and status label via `after(0, ...)` callbacks. Shows messagebox on completion.

---

## UI: `ShortcutsOverlay`

A modal `tk.Toplevel` (460×480), opened by pressing `?`. Two-column layout of sections:

- **Navigation**: ↑/↓ move folders, → expand/enter, ← go up, Enter jump to file list, F focus search, V toggle flat view, Esc cancel search
- **Playback**: Space play/stop, Tab toggle autoplay
- **Set management**: E add to set, Shift+E quick-add, N new set, Q cycle set, Delete remove item
- **Panels**: C waveform editor, X export, Ctrl+T cycle theme, ? shortcuts, Esc close

Each row: `kbd_label` badge + muted description label. Close button + Escape binding.

---

## UI: `AppWindow`

Main controller. Owns all core services and wires the UI together.

**State:** `_current_node: Optional[DirNode]` (selected in browser), `_current_path: Optional[str]` (active path from either browser or set panel), `_in_editor: bool`.

**View switching:**
- `_show_browser()` — `grid_remove()` editor, `grid()` browser, unbind Escape, focus list
- `_show_editor()` — `grid_remove()` browser, `grid()` editor, call `editor.load(_current_path)`, bind Escape → show_browser. Guard: returns early if `_current_path` is None.

**File selection callbacks:**
- `_on_file_select(node)` — sets `_current_node`, `_current_path = node.path`, calls `detail.set_file`, updates playing label
- `_on_set_select(path)` — sets `_current_path = path`, calls `detail.set_file` (selecting a set item enables the editor for that sample via C key)
- `_on_add(node)` — calls `set_panel.add_file`, flashes status
- `_on_quick_add(node)` — calls `set_panel.show_quick_add`

**Global key bindings** (`bind_all`):
- `C` / `c` — toggle editor (open if in browser, close if in editor)
- `E` / `e` — add current browser node to active set; Shift+E for quick-add
- `Q` / `q` — cycle set
- `F` / `f` — focus search
- `X` / `x` — open export panel (only when not in editor)
- `Ctrl+T` — cycle theme; call `_apply_theme()` to push new colours to all direct-colour widgets
- `?` — open shortcuts overlay
- `Space` — toggle playback of `_current_path`
- `Tab` — toggle autoplay

Do not intercept keys when focus is in a `tk.Entry` or `ttk.Entry`.

**State persistence** (JSON at `~/.kit_crafter_config.json`):
Save/restore: `last_folder`, `active_set_index`, full `sets` list (with items and history), `clips` dict (active clip + history per path with all FadeSpec fields), `theme`, `autoplay`. Restore on startup, save on quit and via `atexit`.

**Toolbar:** app name + version (left); "Open folder" button + current path label (center-left); playing indicator label + theme name label (right).

**Playing label** — polls `engine.is_playing()` every 500 ms via `after`; shows "▶ filename" when playing.

---

## `main.py`

```python
root = tk.Tk()
app = AppWindow(root)
if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    app._browser.set_library_root(sys.argv[1])
    app._path_lbl.configure(text=sys.argv[1])
root.mainloop()
```

---

## Key design constraints

- **No audio processing on the main thread.** All waveform loading and metadata reads happen in daemon threads; results are marshalled back with `.after(0, callback)`.
- **Playhead normalisation must use actual file duration**, not the length of the downsampled waveform array. `WaveformCanvas._duration` is set from `engine.file_info(path)["duration"]`, passed as the `duration` parameter to `set_waveform`. The `set_playhead` guard must check `pos_s is not None`, not `if pos_s`, because position 0.0 is valid.
- **Treeview IIDs must be numeric strings**, not file paths, to avoid Tcl parsing errors with brackets, spaces, and slashes in path strings.
- **Chunked list population** (200 items per `after(0, ...)` tick) keeps the UI responsive on large libraries.
- **Theme colours are module-level globals** in `theme.py` (e.g. `theme.SEL_FG`). After `cycle()` or `set_theme()`, call `apply(root)` to re-style all ttk widgets, then manually update any `tk` widgets that use direct colour arguments (listboxes, canvas backgrounds, tab buttons, kbd labels).
- The `SetPanel` item listbox shows a `✂` badge next to items that have an active clip in `ClipModel`.
- Clip save pushes the previous clip to history. History survives save/restore.
