import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import keyboard

from main import OrganizerApp


class HotkeyDispatchTests(unittest.TestCase):
    def make_app(self):
        app = OrganizerApp.__new__(OrganizerApp)
        app.hotkey_capture_active = False
        app._pressed_hotkey_scans = set()
        app._hotkey_requests = queue.Queue(maxsize=64)
        app._shutting_down = False
        app.config = SimpleNamespace(data={})
        app.gui = SimpleNamespace(root=Mock())
        return app

    def test_repeated_keydown_queues_only_one_action_until_keyup(self):
        app = self.make_app()
        action = Mock()
        app.hotkey_actions = {(frozenset(), 30): action}
        down = SimpleNamespace(event_type=keyboard.KEY_DOWN, scan_code=30)
        up = SimpleNamespace(event_type=keyboard.KEY_UP, scan_code=30)
        with patch("main.win32api.GetAsyncKeyState", return_value=0):
            app.global_hook_listener(down)
            app.global_hook_listener(down)
            self.assertEqual(app._hotkey_requests.qsize(), 1)
            app.global_hook_listener(up)
            app.global_hook_listener(down)
        self.assertEqual(app._hotkey_requests.qsize(), 2)

    def test_safe_mode_requires_modifier_release_before_rearming_chord(self):
        app = self.make_app()
        action = Mock()
        app.hotkey_actions = {(frozenset({"alt"}), 30): action}
        down = SimpleNamespace(event_type=keyboard.KEY_DOWN, scan_code=30)
        up = SimpleNamespace(event_type=keyboard.KEY_UP, scan_code=30)

        def alt_held(vk):
            return -1 if vk == 0x12 else 0

        with patch("main.win32api.GetAsyncKeyState", side_effect=alt_held):
            app.global_hook_listener(down)
            app.global_hook_listener(up)
            app.global_hook_listener(down)

        self.assertEqual(app._hotkey_requests.qsize(), 1)

    def test_overlap_mode_rearms_main_key_while_modifier_stays_held(self):
        app = self.make_app()
        app.config.data["hotkey_chord_overlap_enabled"] = True
        action = Mock()
        app.hotkey_actions = {(frozenset({"alt"}), 30): action}
        down = SimpleNamespace(event_type=keyboard.KEY_DOWN, scan_code=30)
        up = SimpleNamespace(event_type=keyboard.KEY_UP, scan_code=30)

        def alt_held(vk):
            return -1 if vk == 0x12 else 0

        with patch("main.win32api.GetAsyncKeyState", side_effect=alt_held):
            app.global_hook_listener(down)
            app.global_hook_listener(up)
            app.global_hook_listener(down)

        self.assertEqual(app._hotkey_requests.qsize(), 2)

    def test_queued_action_runs_on_polling_thread(self):
        app = self.make_app()
        action = Mock()
        app._hotkey_requests.put_nowait(action)
        app._poll_hotkey_requests()
        action.assert_called_once_with()
        app.gui.root.after.assert_called_once_with(10, app._poll_hotkey_requests)

if __name__ == "__main__":
    unittest.main()
