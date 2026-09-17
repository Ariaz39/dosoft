"""Detect the active WAKFU turn from the game's own visual controls."""

import ctypes
import threading
import time

from PIL import Image
import win32gui

from wakfu_debug import write_wakfu_debug


class WakfuTurnVisualWatcher:
    """Watch WAKFU windows for controls visible only during the player's turn.

    WAKFU's shared log has no unambiguous turn-start event.  The end-turn
    button and the six-card bonus selection both identify the active player.
    They deliberately keep independent edge states: the bonus modal must not
    suppress the normal ``Fin du tour`` detection.
    """

    def __init__(self, get_windows, on_turn_started, on_combat_state_changed=None, interval=0.35):
        self.get_windows = get_windows
        self.on_turn_started = on_turn_started
        self.on_combat_state_changed = on_combat_state_changed
        self.interval = interval
        self.combat_active = False
        self.combat_armed_at = None
        self.activation_pending = False
        self.activation_delay_seconds = 2.0
        self.end_turn_states = {}
        self.dimming_states = {}
        self.previous_brightness = {}

    def set_combat_active(self, active, reason="manual"):
        """Arm or disarm focus only on an explicit user action."""
        active = bool(active)
        if self.combat_active == active:
            return
        self.combat_active = active
        self.combat_armed_at = time.monotonic() if active else None
        self.activation_pending = active
        self.end_turn_states.clear()
        self.dimming_states.clear()
        self.previous_brightness.clear()
        write_wakfu_debug(f"COMBAT_{'START' if active else 'END'} reason={reason}")
        if self.on_combat_state_changed:
            self.on_combat_state_changed(active, reason)

    def start(self):
        threading.Thread(
            target=self._watch, daemon=True, name="wakfu-turn-visual-watcher"
        ).start()

    def _watch(self):
        while True:
            try:
                live_handles = set()
                turn_counter_visible = False
                for account in self.get_windows():
                    hwnd = account["hwnd"]
                    live_handles.add(hwnd)
                    has_end_turn, has_bonus, brightness, has_turn_counter = self.get_turn_indicators(hwnd)
                    turn_counter_visible = turn_counter_visible or has_turn_counter
                    had_end_turn = self.end_turn_states.get(hwnd, False)
                    previous_brightness = self.previous_brightness.get(hwnd)
                    has_dimming = self.combat_active and (
                        previous_brightness is not None
                        and brightness <= previous_brightness * 0.72
                        and previous_brightness - brightness >= 15
                    )
                    had_dimming = self.dimming_states.get(hwnd, False)
                    self.end_turn_states[hwnd] = has_end_turn
                    self.dimming_states[hwnd] = has_dimming
                    self.previous_brightness[hwnd] = brightness

                    # Keep the already-tested end-turn path entirely separate
                    # from the bonus-modal paths. The dimming transition is
                    # also independent: WAKFU darkens only the active player's
                    # view while it waits for their bonus choice.
                    trigger_reasons = []
                    if self.combat_active and has_end_turn and not had_end_turn:
                        trigger_reasons.append("end_turn")
                    if self.combat_active and has_dimming and not had_dimming:
                        trigger_reasons.append("screen_dimming")
                    if trigger_reasons:
                        # A manual combat activation may occur while WAKFU is
                        # still repainting its UI.  Never let those transient
                        # frames steal focus: wait two complete seconds, then
                        # evaluate the screen state fresh.
                        if self.combat_active and self.combat_armed_at is not None:
                            elapsed = time.monotonic() - self.combat_armed_at
                            if elapsed < self.activation_delay_seconds:
                                continue
                        self.activation_pending = False
                        reason = "+".join(trigger_reasons)
                        write_wakfu_debug(
                            f"FOCUS_TRIGGER reason={reason} hwnd={hex(hwnd)} combat={self.combat_active} "
                            f"end_turn={has_end_turn} bonus_observation={has_bonus} tour_counter={has_turn_counter} "
                            f"brightness={brightness:.1f} previous={previous_brightness}"
                        )
                        self.on_turn_started(hwnd, reason)
                    elif (
                        self.combat_active
                        and self.activation_pending
                        and self.combat_armed_at is not None
                        and time.monotonic() - self.combat_armed_at >= self.activation_delay_seconds
                        and has_end_turn
                    ):
                        # The end-turn control may have been visible throughout
                        # the arming delay, so it has no new edge to trigger.
                        # Apply it once after the stable two-second wait.
                        self.activation_pending = False
                        reason = "activation_ready"
                        write_wakfu_debug(
                            f"FOCUS_TRIGGER reason={reason} hwnd={hex(hwnd)} combat=True "
                            f"end_turn={has_end_turn} tour_counter={has_turn_counter}"
                        )
                        self.on_turn_started(hwnd, reason)
                self.end_turn_states = {
                    hwnd: state for hwnd, state in self.end_turn_states.items() if hwnd in live_handles
                }
                self.dimming_states = {
                    hwnd: state for hwnd, state in self.dimming_states.items() if hwnd in live_handles
                }
                self.previous_brightness = {
                    hwnd: value for hwnd, value in self.previous_brightness.items() if hwnd in live_handles
                }
                # The ``Tour N`` counter remains visible during every player's
                # and monster's turn. Its disappearance is the visual end of
                # the combat session, so world lighting cannot trigger focus.
                if self.combat_active and not turn_counter_visible:
                    self.set_combat_active(False, "turn_counter_absent")
            except Exception:
                # A closed/recreated Java window must not stop the watcher.
                pass
            time.sleep(self.interval)

    @staticmethod
    def get_turn_indicators(hwnd):
        """Return independent states, brightness and combat HUD visibility."""
        if not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            return False, False, 0, False

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top
        if width < 300 or height < 300:
            return False, False, 0, False

        window_dc = ctypes.windll.user32.GetWindowDC(hwnd)
        memory_dc = ctypes.windll.gdi32.CreateCompatibleDC(window_dc)
        bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(window_dc, width, height)
        old_bitmap = ctypes.windll.gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not ctypes.windll.user32.PrintWindow(hwnd, memory_dc, 2):
                return False, False, 0, False
            # Copy the small lower-right area only. It contains the end-turn
            # button for any normal WAKFU window size.
            box = (int(width * 0.925), int(height * 0.88), int(width * 0.995), int(height * 0.99))
            crop_width, crop_height = box[2] - box[0], box[3] - box[1]
            if crop_width <= 0 or crop_height <= 0:
                return False, False, 0, False

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
            has_turn_counter = WakfuTurnVisualWatcher.has_turn_counter(image)
            return has_end_turn_button, has_bonus_selection, brightness, has_turn_counter
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
    def has_turn_counter(image):
        """Recognize the white ``Tour N`` combat counter at top right."""
        width, height = image.size
        box = (int(width * 0.925), int(height * 0.035), int(width * 0.995), int(height * 0.12))
        pixels = image.crop(box).getdata()
        white_pixels = sum(
            red >= 190 and green >= 190 and blue >= 190 for red, green, blue in pixels
        )
        return white_pixels >= 80

    @staticmethod
    def has_end_turn_button(hwnd):
        """Return only the normal end-turn state (never the bonus modal)."""
        return WakfuTurnVisualWatcher.get_turn_indicators(hwnd)[0]
