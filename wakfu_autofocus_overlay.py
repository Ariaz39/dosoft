"""One persistent, owner-bound WAKFU control for explicit auto-focus arming."""

from __future__ import annotations

import tkinter as tk

import win32con
import win32gui


class WakfuAutofocusOverlay:
    """Keep a single control attached to whichever WAKFU client is active."""

    DEFAULT_POSITION = (0.59, 0.56)
    SIZE = (64, 78)

    def __init__(self, parent_root, config, get_windows, on_toggle):
        self.parent_root = parent_root
        self.config = config
        self.get_windows = get_windows
        self.on_toggle = on_toggle
        self.armed = False
        self.anchor_hwnd = None
        self.anchor_rect = None
        self.drag_offset = None

        self.window = tk.Toplevel(parent_root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        # Owned, not globally topmost: it remains over WAKFU, below other apps.
        self.window.attributes("-topmost", False)
        self.window.configure(bg="#1c252d")
        self.window.resizable(False, False)

        frame = tk.Frame(
            self.window, bg="#1c252d", highlightbackground="#d8b45a",
            highlightthickness=2, width=self.SIZE[0], height=self.SIZE[1],
        )
        frame.pack(fill="both", expand=True)
        handle = tk.Label(frame, text="⋮⋮", bg="#1c252d", fg="#d8b45a", font=("Segoe UI", 8))
        handle.pack(fill="x")
        self.button = tk.Button(
            frame, text="AUTO\nFOCUS", command=self.on_toggle,
            bg="#263641", activebackground="#334b59", fg="#f4e3a1",
            activeforeground="#ffffff", font=("Segoe UI", 8, "bold"),
            bd=0, relief="flat", cursor="hand2", padx=2, pady=3,
        )
        self.button.pack(fill="both", expand=True, padx=2, pady=(0, 2))
        for widget in (frame, handle):
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
            handles = {account["hwnd"] for account in accounts if win32gui.IsWindow(account["hwnd"])}
            if not handles:
                self.window.withdraw()
                self.anchor_hwnd = None
                self.anchor_rect = None
                return

            foreground = win32gui.GetForegroundWindow()
            if foreground in handles and foreground != self.anchor_hwnd:
                self._attach_to(foreground)
            elif self.anchor_hwnd not in handles:
                self._attach_to(foreground if foreground in handles else next(iter(handles)))

            if self.anchor_hwnd and not self.drag_offset:
                self._place_if_window_changed()
            self.window.deiconify()
        finally:
            self.parent_root.after(350, self._refresh)

    def _attach_to(self, hwnd):
        self.anchor_hwnd = hwnd
        self.anchor_rect = None
        try:
            # Re-own the same physical popup; no duplicate button is created.
            win32gui.SetWindowLong(self.window.winfo_id(), win32con.GWL_HWNDPARENT, hwnd)
        except Exception:
            pass
        self._place_if_window_changed()

    def _place_if_window_changed(self):
        try:
            rect = win32gui.GetWindowRect(self.anchor_hwnd)
            if self.anchor_rect == rect:
                return
            left, top, right, bottom = rect
            width, height = right - left, bottom - top
            position = self.config.data.get("wakfu_autofocus_overlay_position", list(self.DEFAULT_POSITION))
            x_ratio, y_ratio = position if isinstance(position, list) and len(position) == 2 else self.DEFAULT_POSITION
            x = left + int(width * max(0.0, min(0.94, x_ratio)))
            y = top + int(height * max(0.0, min(0.90, y_ratio)))
            self.window.geometry(f"{self.SIZE[0]}x{self.SIZE[1]}+{x}+{y}")
            self.anchor_rect = rect
        except Exception:
            pass

    def _start_drag(self, event):
        self.drag_offset = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag(self, event):
        if self.drag_offset:
            x_offset, y_offset = self.drag_offset
            self.window.geometry(f"+{event.x_root - x_offset}+{event.y_root - y_offset}")

    def _save_position(self, _event):
        if not self.drag_offset or not self.anchor_hwnd:
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
            # Stay exactly at the chosen location until the WAKFU window moves.
            self.anchor_rect = (left, top, right, bottom)
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
