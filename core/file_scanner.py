"""
File system scanning and navigation model.

Provides both a folder-tree view and a flat view (all audio files under a
given path in one list), mirroring Kit Crafter's V-toggle behaviour.
"""
from __future__ import annotations
import os
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".opus"}


@dataclass
class DirNode:
    """One node in the folder tree (dir or audio file)."""
    path: str
    name: str
    is_dir: bool
    children: List["DirNode"] = field(default_factory=list)
    parent: Optional["DirNode"] = field(default=None, repr=False)

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return isinstance(other, DirNode) and self.path == other.path


class FileScanner:
    """
    Manages directory tree loading and provides current-view lists.

    flat_view=False  → only immediate children of current_dir are shown.
    flat_view=True   → all audio files under current_dir are shown recursively.
    """

    def __init__(self) -> None:
        self.root: Optional[DirNode] = None
        self.current_dir: Optional[DirNode] = None
        self._flat_view: bool = False
        self._file_list: List[DirNode] = []        # cached, recomputed on dir change
        self._node_by_path: Dict[str, DirNode] = {}  # O(1) path → node lookup
        self._scan_id: int = 0                     # incremented each scan to discard stale results

    # ------------------------------------------------------------------ loading

    def set_root(self, path: str, on_done: Optional[Callable] = None) -> None:
        """Scan a directory as the library root in a background thread.

        on_done is called on the background thread when the scan completes;
        callers that need to update UI should schedule it back to the main thread
        (e.g. ``lambda: widget.after(0, callback)``).
        """
        self._scan_id += 1
        my_id = self._scan_id
        self.root = None
        self.current_dir = None
        self._file_list = []
        self._node_by_path = {}

        def _scan() -> None:
            node_map: Dict[str, DirNode] = {}
            tree = self._build_tree(path, parent=None, node_map=node_map)
            if self._scan_id != my_id:
                return  # a newer scan was started; discard this result
            self._node_by_path = node_map
            self.root = tree
            self.current_dir = tree
            self._refresh_file_list()
            if on_done:
                on_done()

        threading.Thread(target=_scan, daemon=True).start()

    def _build_tree(
        self,
        path: str,
        parent: Optional[DirNode],
        node_map: Dict[str, DirNode],
    ) -> Optional[DirNode]:
        try:
            name = os.path.basename(path) or path
            node = DirNode(path=path, name=name, is_dir=os.path.isdir(path), parent=parent)
            node_map[path] = node
            if node.is_dir:
                for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
                    if entry.name.startswith("."):
                        continue
                    if entry.is_dir():
                        child = self._build_tree(entry.path, node, node_map)
                        if child:
                            node.children.append(child)
                    elif os.path.splitext(entry.name)[1].lower() in AUDIO_EXTS:
                        child = DirNode(path=entry.path, name=entry.name, is_dir=False, parent=node)
                        node.children.append(child)
                        node_map[entry.path] = child
            return node
        except PermissionError:
            return None

    # ------------------------------------------------------------------ lookup

    def get_node(self, path: str) -> Optional[DirNode]:
        """O(1) lookup of a DirNode by its filesystem path."""
        return self._node_by_path.get(path)

    # ------------------------------------------------------------------ navigation

    @property
    def flat_view(self) -> bool:
        return self._flat_view

    def toggle_flat_view(self) -> None:
        self._flat_view = not self._flat_view
        self._refresh_file_list()

    def set_current_dir(self, node: DirNode) -> None:
        if node.is_dir:
            self.current_dir = node
            self._refresh_file_list()

    def navigate_up(self) -> None:
        if self.current_dir and self.current_dir.parent:
            self.set_current_dir(self.current_dir.parent)

    # ------------------------------------------------------------------ view

    def _refresh_file_list(self) -> None:
        if self.current_dir is None:
            self._file_list = []
            return
        if self._flat_view:
            self._file_list = self._collect_all_audio(self.current_dir)
        else:
            self._file_list = [
                c for c in self.current_dir.children if not c.is_dir
            ]

    def _collect_all_audio(self, node: DirNode) -> List[DirNode]:
        files: List[DirNode] = []
        for child in node.children:
            if child.is_dir:
                files.extend(self._collect_all_audio(child))
            else:
                files.append(child)
        return files

    @property
    def file_list(self) -> List[DirNode]:
        """Audio files visible in the center list for current context."""
        return self._file_list

    @property
    def dir_children(self) -> List[DirNode]:
        """Subdirectories of current_dir."""
        if self.current_dir is None:
            return []
        return [c for c in self.current_dir.children if c.is_dir]

    def search(self, query: str) -> List[DirNode]:
        """Case-insensitive recursive search from root."""
        if self.root is None:
            return []
        q = query.lower()
        return self._search_node(self.root, q)

    def _search_node(self, node: DirNode, q: str) -> List[DirNode]:
        results: List[DirNode] = []
        for child in node.children:
            if child.is_dir:
                results.extend(self._search_node(child, q))
            elif q in child.name.lower():
                results.append(child)
        return results
