"""Persistent, owner-bound WAKFU controls for explicit auto-focus arming."""

from __future__ import annotations

import tkinter as tk

import win32con
import win32gui


class WakfuAutofocusOverlay:
    """Keep one movable control above each WAKFU client, never other apps."""

    DEFAULT_POSITION = (0.59, 0.56)
    SIZE = (64, 78)

    def __init__(self, parent_root, config, get_windows, on_toggle):
        self.parent_root = parent_root
        self.config = config
        self.get_windows = get_windows
        self.on_toggle = on_toggle
        self.armed = False
        self.overlays = {}
        self.parent_root.after(350, self._refresh)

    def _is_enabled(self):
        return (
            self.config.data.get("game_version") == "Wakfu"
            and self.config.data.get("auto_focus_wakfu", False)
        )

    def _create_overlay(self, hwnd):
        window = tk.Toplevel(self.parent_root)
        window.withdraw()
        window.overrideredirect(True)
        # It is owned by its WAKFU window, not globally topmost: it stays over
        # WAKFU while remaining below any unrelated foreground application.
        window.attributes("-topmost", False)
        window.configure(bg="#1c252d")
        window.resizable(False, False)

        frame = tk.Frame(
            window, bg="#1c252d", highlightbackground="#d8b45a",
            highlightthickness=2, width=self.SIZE[0], height=self.SIZE[1],
        )
        frame.pack(fill="both", expand=True)
        handle = tk.Label(frame, text="⋮⋮", bg="#1c252d", fg="#d8b45a", font=("Segoe UI", 8))
        handle.pack(fill="x")
        button = tk.Button(
            frame, text="AUTO\nFOCUS", command=self.on_toggle,
            bg="#263641", activebackground="#334b59", fg="#f4e3a1",
            activeforeground="#ffffff", font=("Segoe UI", 8, "bold"),
            bd=0, relief="flat", cursor="hand2", padx=2, pady=3,
        )
        button.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        entry = {"window": window, "button": button, "rect": None, "drag": None}
        for widget in (frame, handle):
            widget.bind("<ButtonPress-1>", lambda event, target=hwnd: self._start_drag(target, event))
            widget.bind("<B1-Motion>", lambda event, target=hwnd: self._drag(target, event))
            widget.bind("<ButtonRelease-1>", lambda event, target=hwnd: self._save_position(target))

        self.overlays[hwnd] = entry
        try:
            win32gui.SetWindowLong(window.winfo_id(), win32con.GWL_HWNDPARENT, hwnd)
        except Exception:
            pass
        self._apply_style(entry)
        return entry

    def _apply_style(self, entry):
        if self.armed:
            entry["button"].configure(text="COMBAT\nACTIF", bg="#2f6b57", activebackground="#3c8069")
        else:
            entry["button"].configure(text="AUTO\nFOCUS", bg="#263641", activebackground="#334b59")

    def _refresh(self):
        try:
            if not self._is_enabled():
                self._hide_all()
            else:
                live_handles = {account["hwnd"] for account in self.get_windows()}
                for hwnd in live_handles:
                    if not win32gui.IsWindow(hwnd):
                        continue
                    entry = self.overlays.get(hwnd) or self._create_overlay(hwnd)
                    self._place_if_needed(hwnd, entry)
                    entry["window"].deiconify()
                for hwnd, entry in list(self.overlays.items()):
                    if hwnd not in live_handles or not win32gui.IsWindow(hwnd):
                        entry["window"].destroy()
                        del self.overlays[hwnd]
        finally:
            self.parent_root.after(350, self._refresh)

    def _place_if_needed(self, hwnd, entry):
        try:
            rect = win32gui.GetWindowRect(hwnd)
            if entry["rect"] == rect:
                return
            left, top, right, bottom = rect
            width, height = right - left, bottom - top
            position = self.config.data.get("wakfu_autofocus_overlay_position", list(self.DEFAULT_POSITION))
            x_ratio, y_ratio = position if isinstance(position, list) and len(position) == 2 else self.DEFAULT_POSITION
            x = left + int(width * max(0.0, min(0.94, x_ratio)))
            y = top + int(height * max(0.0, min(0.90, y_ratio)))
            entry["window"].geometry(f"{self.SIZE[0]}x{self.SIZE[1]}+{x}+{y}")
            entry["rect"] = rect
        except Exception:
            pass

    def _start_drag(self, hwnd, event):
        entry = self.overlays.get(hwnd)
        if entry:
            entry["drag"] = (event.x_root - entry["window"].winfo_x(), event.y_root - entry["window"].winfo_y())

    def _drag(self, hwnd, event):
        entry = self.overlays.get(hwnd)
        if entry and entry["drag"]:
            x_offset, y_offset = entry["drag"]
            entry["window"].geometry(f"+{event.x_root - x_offset}+{event.y_root - y_offset}")

    def _save_position(self, hwnd):
        entry = self.overlays.get(hwnd)
        if not entry or not entry["drag"]:
            return
        entry["drag"] = None
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width, height = right - left, bottom - top
            x_ratio = (entry["window"].winfo_x() - left) / max(width, 1)
            y_ratio = (entry["window"].winfo_y() - top) / max(height, 1)
            self.config.data["wakfu_autofocus_overlay_position"] = [
                round(max(0.0, min(0.94, x_ratio)), 4),
                round(max(0.0, min(0.90, y_ratio)), 4),
            ]
            self.config.save()
            # A dragged overlay stays exactly there; repositioning happens only
            # after its WAKFU window is moved or resized.
            entry["rect"] = (left, top, right, bottom)
        except Exception:
            pass

    def _hide_all(self):
        for entry in self.overlays.values():
            entry["window"].withdraw()

    def set_armed(self, armed):
        self.armed = armed
        for entry in self.overlays.values():
            self._apply_style(entry)

    def sync(self):
        if not self._is_enabled():
            self._hide_all()
