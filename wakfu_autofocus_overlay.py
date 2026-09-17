"""Small draggable WAKFU overlay used to explicitly arm auto-focus."""

from __future__ import annotations

import tkinter as tk
import win32gui


class WakfuAutofocusOverlay:
    """Show an always-on-WAKFU control only while a WAKFU window is active."""

    DEFAULT_POSITION = (0.59, 0.56)

    def __init__(self, parent_root, config, get_windows, on_toggle):
        self.parent_root = parent_root
        self.config = config
        self.get_windows = get_windows
        self.on_toggle = on_toggle
        self.armed = False
        self.anchor_hwnd = None
        self.drag_offset = None

        self.window = tk.Toplevel(parent_root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#1c252d")
        self.window.resizable(False, False)

        self.frame = tk.Frame(
            self.window, bg="#1c252d", highlightbackground="#d8b45a",
            highlightthickness=2, width=64, height=78,
        )
        self.frame.pack(fill="both", expand=True)
        self.handle = tk.Label(self.frame, text="⋮⋮", bg="#1c252d", fg="#d8b45a", font=("Segoe UI", 8))
        self.handle.pack(fill="x")
        self.button = tk.Button(
            self.frame, text="AUTO\nFOCUS", command=self.on_toggle,
            bg="#263641", activebackground="#334b59", fg="#f4e3a1",
            activeforeground="#ffffff", font=("Segoe UI", 8, "bold"),
            bd=0, relief="flat", cursor="hand2", padx=2, pady=3,
        )
        self.button.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        for widget in (self.frame, self.handle):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", self._save_position)

        self.parent_root.after(350, self._refresh)

    def _is_enabled(self):
        return (
            self.config.data.get("game_version") == "Wakfu"
            and self.config.data.get("auto_focus_wakfu", False)
        )

    def _refresh(self):
        try:
            accounts = self.get_windows() if self._is_enabled() else []
            hwnd_by_handle = {account["hwnd"] for account in accounts}
            foreground = win32gui.GetForegroundWindow()
            overlay_foreground = foreground == self.window.winfo_id()
            if foreground in hwnd_by_handle or (overlay_foreground and self.anchor_hwnd in hwnd_by_handle):
                if foreground in hwnd_by_handle:
                    self.anchor_hwnd = foreground
                if not self.drag_offset:
                    self._place_on_wakfu_window(foreground)
                self.window.deiconify()
                self.window.lift()
            else:
                self.window.withdraw()
        finally:
            self.parent_root.after(350, self._refresh)

    def _place_on_wakfu_window(self, hwnd):
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width, height = right - left, bottom - top
            position = self.config.data.get(
                "wakfu_autofocus_overlay_position", list(self.DEFAULT_POSITION)
            )
            x_ratio, y_ratio = position if len(position) == 2 else self.DEFAULT_POSITION
            x = left + int(width * max(0.0, min(0.94, x_ratio)))
            y = top + int(height * max(0.0, min(0.90, y_ratio)))
            self.window.geometry(f"64x78+{x}+{y}")
        except Exception:
            pass

    def _start_drag(self, event):
        self.drag_offset = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag(self, event):
        if self.drag_offset:
            self.window.geometry(
                f"+{event.x_root - self.drag_offset[0]}+{event.y_root - self.drag_offset[1]}"
            )

    def _save_position(self, _event):
        if not self.drag_offset:
            return
        self.drag_offset = None
        try:
            left, top, right, bottom = win32gui.GetWindowRect(self.anchor_hwnd)
            width, height = right - left, bottom - top
            x_ratio = (self.window.winfo_x() - left) / max(width, 1)
            y_ratio = (self.window.winfo_y() - top) / max(height, 1)
            self.config.data["wakfu_autofocus_overlay_position"] = [
                round(max(0.0, min(0.94, x_ratio)), 4),
                round(max(0.0, min(0.90, y_ratio)), 4),
            ]
            self.config.save()
        except Exception:
            pass

    def set_armed(self, armed):
        self.armed = armed
        if armed:
            self.button.configure(text="COMBAT\nACTIF", bg="#2f6b57", activebackground="#3c8069")
        else:
            self.button.configure(text="AUTO\nFOCUS", bg="#263641", activebackground="#334b59")

    def sync(self):
        if not self._is_enabled():
            self.window.withdraw()
