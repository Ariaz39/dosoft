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
    They deliberately keep independent edge states: the bonus modal must not
    suppress the normal ``Fin du tour`` detection.
    """

    def __init__(self, get_windows, on_turn_started, is_combat_active, interval=0.35):
        self.get_windows = get_windows
        self.on_turn_started = on_turn_started
        self.is_combat_active = is_combat_active
        self.interval = interval
        self.end_turn_states = {}
        self.bonus_states = {}
        self.dimming_states = {}
        self.previous_brightness = {}

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
                    has_end_turn, has_bonus, brightness = self.get_turn_indicators(hwnd)
                    had_end_turn = self.end_turn_states.get(hwnd, False)
                    had_bonus = self.bonus_states.get(hwnd, False)
                    previous_brightness = self.previous_brightness.get(hwnd)
                    has_dimming = self.is_combat_active() and (
                        previous_brightness is not None
                        and brightness <= previous_brightness * 0.72
                        and previous_brightness - brightness >= 15
                    )
                    had_dimming = self.dimming_states.get(hwnd, False)
                    self.end_turn_states[hwnd] = has_end_turn
                    self.bonus_states[hwnd] = has_bonus
                    self.dimming_states[hwnd] = has_dimming
                    self.previous_brightness[hwnd] = brightness

                    # Keep the already-tested end-turn path entirely separate
                    # from the bonus-modal paths. The dimming transition is
                    # also independent: WAKFU darkens only the active player's
                    # view while it waits for their bonus choice.
                    if (
                        (has_end_turn and not had_end_turn)
                        or (has_bonus and not had_bonus)
                        or (has_dimming and not had_dimming)
                    ):
                        self.on_turn_started(hwnd)
                self.end_turn_states = {
                    hwnd: state for hwnd, state in self.end_turn_states.items() if hwnd in live_handles
                }
                self.bonus_states = {
                    hwnd: state for hwnd, state in self.bonus_states.items() if hwnd in live_handles
                }
                self.dimming_states = {
                    hwnd: state for hwnd, state in self.dimming_states.items() if hwnd in live_handles
                }
                self.previous_brightness = {
                    hwnd: value for hwnd, value in self.previous_brightness.items() if hwnd in live_handles
                }
            except Exception:
                # A closed/recreated Java window must not stop the watcher.
                pass
            time.sleep(self.interval)

    @staticmethod
    def get_turn_indicators(hwnd):
        """Return independent states and average game-view brightness."""
        if not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            return False, False, 0

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top
        if width < 300 or height < 300:
            return False, False, 0

        window_dc = ctypes.windll.user32.GetWindowDC(hwnd)
        memory_dc = ctypes.windll.gdi32.CreateCompatibleDC(window_dc)
        bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(window_dc, width, height)
        old_bitmap = ctypes.windll.gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not ctypes.windll.user32.PrintWindow(hwnd, memory_dc, 2):
                return False, False, 0
            # Copy the small lower-right area only. It contains the end-turn
            # button for any normal WAKFU window size.
            box = (int(width * 0.925), int(height * 0.88), int(width * 0.995), int(height * 0.99))
            crop_width, crop_height = box[2] - box[0], box[3] - box[1]
            if crop_width <= 0 or crop_height <= 0:
                return False, False, 0

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
            has_bonus_selection = WakfuTurnVisualWatcher.has_bonus_selection_modal(image)
            # The bonus modal dims the full map behind it. Sample the central
            # game area (without title bar and bottom action bar) so an abrupt
            # per-window darkening is detectable independently of its cards.
            scene = image.crop((int(width * 0.10), int(height * 0.15), int(width * 0.90), int(height * 0.75)))
            red, green, blue = scene.resize((1, 1)).getpixel((0, 0))
            brightness = (red + green + blue) / 3
            return has_end_turn_button, has_bonus_selection, brightness
        finally:
            ctypes.windll.gdi32.SelectObject(memory_dc, old_bitmap)
            ctypes.windll.gdi32.DeleteObject(bitmap)
            ctypes.windll.gdi32.DeleteDC(memory_dc)
            ctypes.windll.user32.ReleaseDC(hwnd, window_dc)

    @staticmethod
    def has_bonus_selection_modal(image):
        """Recognize the enabled ``Passer`` button in the bonus panel."""
        width, height = image.size
        # The cards are visible in every client.  Only the window whose turn it
        # is renders the actionable ``Passer`` button, directly below them.
        # Restricting the check to the word/button strip prevents the shared
        # six-card display from stealing focus on inactive clients.
        box = (int(width * 0.37), int(height * 0.67), int(width * 0.63), int(height * 0.715))
        crop_width, crop_height = box[2] - box[0], box[3] - box[1]
        if crop_width <= 0 or crop_height <= 0:
            return False

        pixels = image.crop(box).getdata()
        light_text_pixels = sum(
            red >= 200 and green >= 200 and blue >= 200
            for red, green, blue in pixels
        )
        return light_text_pixels / (crop_width * crop_height) >= 0.025

    @staticmethod
    def has_end_turn_button(hwnd):
        """Return only the normal end-turn state (never the bonus modal)."""
        return WakfuTurnVisualWatcher.get_turn_indicators(hwnd)[0]
