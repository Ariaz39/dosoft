"""A fixed, global WAKFU-only control for explicit auto-focus arming."""

from __future__ import annotations

import os
import tkinter as tk

from PIL import Image, ImageTk
import win32gui

from resource_paths import resource_path


class WakfuAutofocusOverlay:
    """Keep one fixed overlay visible whenever WAKFU auto-focus is enabled."""

    DEFAULT_POSITION = (0.59, 0.56)
    SIZE = (64, 78)

    def __init__(self, parent_root, config, get_windows, on_toggle):
        self.parent_root = parent_root
        self.config = config
        self.get_windows = get_windows
        self.on_toggle = on_toggle
        self.armed = False
        self.drag_offset = None
        self.position_initialized = False

        self.window = tk.Toplevel(parent_root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        # The user explicitly wants this control permanently on top while the
        # WAKFU Auto-Focus option is enabled.
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#1c252d")
        self.window.resizable(False, False)

        frame = tk.Frame(
            self.window, bg="#1c252d", highlightbackground="#d8b45a",
            highlightthickness=2, width=self.SIZE[0], height=self.SIZE[1],
        )
        frame.pack(fill="both", expand=True)
        handle = tk.Label(frame, text="⋮⋮", bg="#1c252d", fg="#d8b45a", font=("Segoe UI", 8))
        handle.pack(fill="x")

        self.focus_image = self._load_focus_image()
        self.button = tk.Button(
            frame, text="" if self.focus_image else "FOCUS", image=self.focus_image,
            command=self.on_toggle, bg="#263641", activebackground="#334b59",
            bd=0, relief="flat", cursor="hand2", padx=2, pady=2,
        )
        self.button.pack(fill="both", expand=True, padx=2, pady=(0, 2))
        for widget in (frame, handle):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", self._save_position)

        self.parent_root.after(250, self._refresh)

    def _load_focus_image(self):
        path = resource_path("resources", "skin", "focus.png")
        if not os.path.exists(path):
            return None
        try:
            image = Image.open(path).resize((48, 48), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _is_enabled(self):
        return (
            self.config.data.get("game_version") == "Wakfu"
            and self.config.data.get("auto_focus_wakfu", False)
        )

    def _refresh(self):
        try:
            accounts = self.get_windows() if self._is_enabled() else []
            handles = {account["hwnd"] for account in accounts if win32gui.IsWindow(account["hwnd"])}
            if handles:
                if not self.position_initialized:
                    self._restore_position(next(iter(handles)))
                self.window.deiconify()
                self.window.lift()
            else:
                self.window.withdraw()
        finally:
            self.parent_root.after(250, self._refresh)

    def _restore_position(self, fallback_hwnd):
        saved_position = self.config.data.get("wakfu_autofocus_overlay_screen_position")
        if isinstance(saved_position, list) and len(saved_position) == 2:
            x, y = saved_position
        else:
            left, top, right, bottom = win32gui.GetWindowRect(fallback_hwnd)
            ratio = self.config.data.get("wakfu_autofocus_overlay_position", list(self.DEFAULT_POSITION))
            x_ratio, y_ratio = ratio if isinstance(ratio, list) and len(ratio) == 2 else self.DEFAULT_POSITION
            x = left + int((right - left) * x_ratio)
            y = top + int((bottom - top) * y_ratio)
        self.window.geometry(f"{self.SIZE[0]}x{self.SIZE[1]}+{int(x)}+{int(y)}")
        self.position_initialized = True

    def _start_drag(self, event):
        self.drag_offset = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag(self, event):
        if self.drag_offset:
            x_offset, y_offset = self.drag_offset
            self.window.geometry(f"+{event.x_root - x_offset}+{event.y_root - y_offset}")

    def _save_position(self, _event):
        if not self.drag_offset:
            return
        self.drag_offset = None
        self.config.data["wakfu_autofocus_overlay_screen_position"] = [
            self.window.winfo_x(), self.window.winfo_y()
        ]
        self.config.save()

    def set_armed(self, armed):
        self.armed = armed
        if armed:
            self.button.configure(bg="#2f6b57", activebackground="#3c8069")
        else:
            self.button.configure(bg="#263641", activebackground="#334b59")

    def sync(self):
        if not self._is_enabled():
            self.window.withdraw()
