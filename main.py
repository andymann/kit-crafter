#!/usr/bin/env python3
"""
Kit Crafter — keyboard-first sample manager.

Usage:
    python main.py [library_path]

Dependencies (pip install):
    pygame  soundfile  numpy  pydub

Optional (for BPM/key detection):
    librosa
"""
import sys
import os
import tkinter as tk

# ensure the project root is on sys.path when run from any cwd
sys.path.insert(0, os.path.dirname(__file__))

from ui.app_window import AppWindow


def main() -> None:
    root = tk.Tk()
    app = AppWindow(root)

    # if a path was passed on the command line, open it immediately
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        app._browser.set_library_root(sys.argv[1])
        app._path_lbl.configure(text=sys.argv[1])

    root.mainloop()


if __name__ == "__main__":
    main()
