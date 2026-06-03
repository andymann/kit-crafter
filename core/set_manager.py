"""
Set management: create, switch, add/remove samples, history per set.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid


@dataclass
class SetItem:
    path: str
    name: str          # display name (editable)
    clip_id: Optional[str] = None   # reference to ClipModel entry


@dataclass
class SampleSet:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "New set"
    items: List[SetItem] = field(default_factory=list)
    history: List[SetItem] = field(default_factory=list)  # removed items

    def add(self, path: str, name: str) -> bool:
        """Add a file. Returns False if already present."""
        if any(i.path == path for i in self.items):
            return False
        self.items.append(SetItem(path=path, name=name))
        return True

    def remove(self, path: str) -> None:
        item = next((i for i in self.items if i.path == path), None)
        if item:
            self.items.remove(item)
            self.history.insert(0, item)   # prepend so newest is first

    def restore(self, path: str) -> None:
        item = next((i for i in self.history if i.path == path), None)
        if item:
            self.history.remove(item)
            self.items.append(item)

    def contains(self, path: str) -> bool:
        return any(i.path == path for i in self.items)

    def rename_item(self, path: str, new_name: str) -> None:
        for item in self.items:
            if item.path == path:
                item.name = new_name
                return


class SetManager:
    """Manages the collection of sets and the currently active one."""

    def __init__(self) -> None:
        default = SampleSet(name="Set 1")
        self._sets: List[SampleSet] = [default]
        self._active_index: int = 0

    # ------------------------------------------------------------------ sets

    def new_set(self, name: Optional[str] = None) -> SampleSet:
        s = SampleSet(name=name or f"Set {len(self._sets) + 1}")
        self._sets.append(s)
        self._active_index = len(self._sets) - 1
        return s

    def remove_set(self, set_id: str) -> None:
        idx = self._index_of(set_id)
        if idx is None or len(self._sets) <= 1:
            return
        self._sets.pop(idx)
        self._active_index = max(0, min(self._active_index, len(self._sets) - 1))

    def rename_set(self, set_id: str, name: str) -> None:
        s = self.get(set_id)
        if s:
            s.name = name

    # ------------------------------------------------------------------ active

    @property
    def active(self) -> SampleSet:
        return self._sets[self._active_index]

    def cycle_active(self) -> SampleSet:
        self._active_index = (self._active_index + 1) % len(self._sets)
        return self.active

    def set_active(self, set_id: str) -> None:
        idx = self._index_of(set_id)
        if idx is not None:
            self._active_index = idx

    # ------------------------------------------------------------------ items

    def add_to_active(self, path: str, name: Optional[str] = None) -> bool:
        return self.active.add(path, name or self._basename(path))

    def add_to_set(self, set_id: str, path: str, name: Optional[str] = None) -> bool:
        s = self.get(set_id)
        if s:
            return s.add(path, name or self._basename(path))
        return False

    def remove_from_active(self, path: str) -> None:
        self.active.remove(path)

    # ------------------------------------------------------------------ query

    @property
    def sets(self) -> List[SampleSet]:
        return list(self._sets)

    def get(self, set_id: str) -> Optional[SampleSet]:
        return next((s for s in self._sets if s.id == set_id), None)

    def _index_of(self, set_id: str) -> Optional[int]:
        for i, s in enumerate(self._sets):
            if s.id == set_id:
                return i
        return None

    @staticmethod
    def _basename(path: str) -> str:
        import os
        return os.path.splitext(os.path.basename(path))[0]
