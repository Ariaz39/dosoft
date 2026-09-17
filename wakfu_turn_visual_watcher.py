"""Detect the active WAKFU turn from the game's own visual controls."""

import ctypes
import threading
import time

from PIL import Image
import win32gui


class WakfuTurnVisualWatcher:
    """Watch WAKFU windows for controls visible only during the player's turn.

    WAKFU's shared log has no unambiguous turn-start event.  The end-turn
    button and the six-card bonus selection both identify the active player.
    """

    def __init__(self, get_windows, on_turn_started, interval=0.35):
        self.get_windows = get_windows
        self.on_turn_started = on_turn_started
        self.interval = interval
        self.states = {}

    def start(self):
        threading.Thread(
            target=self._watch, daemon=True, name="wakfu-turn-visual-watcher"
        ).start()

    def _watch(self):
        while True:
            try:
                live_handles = set()
                for account in self.get_windows():
                    hwnd = account["hwnd"]
                    live_handles.add(hwnd)
                    is_active = self.has_active_turn_indicator(hwnd)
                    was_active = self.states.get(hwnd, False)
                    self.states[hwnd] = is_active
                    if is_active and not was_active:
                        self.on_turn_started(hwnd)
                self.states = {
                    hwnd: state for hwnd, state in self.states.items() if hwnd in live_handles
                }
            except Exception:
                # A closed/recreated Java window must not stop the watcher.
                pass
            time.sleep(self.interval)

    @staticmethod
    def has_active_turn_indicator(hwnd):
        """Return whether an end-turn or bonus-selection control is visible."""
        if not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            return False

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top
        if width < 300 or height < 300:
            return False

        window_dc = ctypes.windll.user32.GetWindowDC(hwnd)
        memory_dc = ctypes.windll.gdi32.CreateCompatibleDC(window_dc)
        bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(window_dc, width, height)
        old_bitmap = ctypes.windll.gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not ctypes.windll.user32.PrintWindow(hwnd, memory_dc, 2):
                return False
            # Copy the small lower-right area only. It contains the end-turn
            # button for any normal WAKFU window size.
            box = (int(width * 0.925), int(height * 0.88), int(width * 0.995), int(height * 0.99))
            crop_width, crop_height = box[2] - box[0], box[3] - box[1]
            if crop_width <= 0 or crop_height <= 0:
                return False

            buffer = ctypes.create_string_buffer(width * height * 4)

            class BitmapInfoHeader(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            class BitmapInfo(ctypes.Structure):
                _fields_ = [("bmiHeader", BitmapInfoHeader), ("bmiColors", ctypes.c_uint32 * 3)]

            info = BitmapInfo()
            info.bmiHeader = BitmapInfoHeader(
                ctypes.sizeof(BitmapInfoHeader), width, -height, 1, 32, 0, 0, 0, 0, 0, 0
            )
            ctypes.windll.gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)
            image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
            pixels = image.crop(box).getdata()
            beige_pixels = sum(
                red >= 180 and green >= 150 and blue <= 145 and red - green <= 60 and green - blue >= 25
                for red, green, blue in pixels
            )
            has_end_turn_button = beige_pixels / (crop_width * crop_height) >= 0.28
            return has_end_turn_button or WakfuTurnVisualWatcher.has_bonus_selection_modal(image)
        finally:
            ctypes.windll.gdi32.SelectObject(memory_dc, old_bitmap)
            ctypes.windll.gdi32.DeleteObject(bitmap)
            ctypes.windll.gdi32.DeleteDC(memory_dc)
            ctypes.windll.user32.ReleaseDC(hwnd, window_dc)

    @staticmethod
    def has_bonus_selection_modal(image):
        """Recognize the central six-card bonus modal shown every three turns."""
        width, height = image.size
        box = (int(width * 0.39), int(height * 0.25), int(width * 0.61), int(height * 0.73))
        crop_width, crop_height = box[2] - box[0], box[3] - box[1]
        if crop_width <= 0 or crop_height <= 0:
            return False

        # The six offered cards form a compact group of vivid yellow, green,
        # cyan, red and purple tiles at the centre of the dimmed game view.
        pixels = image.crop(box).getdata()
        vivid_pixels = sum(
            max(red, green, blue) >= 180 and max(red, green, blue) - min(red, green, blue) >= 130
            for red, green, blue in pixels
        )
        return vivid_pixels / (crop_width * crop_height) >= 0.05

    @staticmethod
    def has_end_turn_button(hwnd):
        """Compatibility alias used by existing diagnostic tests."""
        return WakfuTurnVisualWatcher.has_active_turn_indicator(hwnd)
