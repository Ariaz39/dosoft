import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from character_bar import CharacterQuickBar
from logic import DofusLogic


class FocusSwitchPerformanceTests(unittest.TestCase):
    def test_direct_focus_sends_one_activation_request(self):
        callback = Mock()
        logic = DofusLogic(SimpleNamespace(data={}), callback)
        hwnd = 42

        with (
            patch("logic.win32gui.IsWindow", return_value=True),
            patch("logic.win32gui.IsIconic", return_value=False),
            patch("logic.win32process.GetWindowThreadProcessId", return_value=(5, 7)),
            patch("logic.win32gui.SetForegroundWindow") as activate,
            patch("logic.win32gui.BringWindowToTop") as duplicate_activate,
            patch("logic.win32gui.GetForegroundWindow", return_value=hwnd),
        ):
            self.assertTrue(logic.focus_window(hwnd))

        activate.assert_called_once_with(hwnd)
        duplicate_activate.assert_not_called()
        callback.assert_called_once_with(hwnd)

    def test_refused_direct_focus_uses_attached_input_fallback(self):
        callback = Mock()
        logic = DofusLogic(SimpleNamespace(data={}), callback)
        hwnd = 42

        with (
            patch("logic.win32gui.IsWindow", return_value=True),
            patch("logic.win32gui.IsIconic", return_value=False),
            patch("logic.win32process.GetWindowThreadProcessId", return_value=(5, 7)),
            patch("logic.win32gui.SetForegroundWindow"),
            patch("logic.win32gui.GetForegroundWindow", side_effect=[99, hwnd]),
            patch.object(logic, "_attach_and_set_foreground", return_value=True) as fallback,
        ):
            self.assertTrue(logic.focus_window(hwnd))

        fallback.assert_called_once_with(hwnd)
        self.assertIn("strategy=attach_thread_input", logic.last_focus_debug)
        callback.assert_called_once_with(hwnd)

    def test_hidden_character_bar_does_not_repaint_cards(self):
        bar = CharacterQuickBar.__new__(CharacterQuickBar)
        bar.cards = [(Mock(), {"hwnd": 42})]
        bar.window = Mock()
        bar.window.winfo_viewable.return_value = False
        bar._last_observed_foreground = 0
        bar._last_foreground = 0
        bar._pending_foreground = 0
        bar._selected_hwnd = 0
        bar.debug = Mock()
        bar.apply_card_states = Mock()

        with patch("character_bar.win32gui.GetForegroundWindow", return_value=42):
            bar.update_card_states()

        self.assertEqual(bar._selected_hwnd, 42)
        bar.apply_card_states.assert_not_called()

    def test_hidden_character_bar_does_not_poll_foreground(self):
        bar = CharacterQuickBar.__new__(CharacterQuickBar)
        bar.config = SimpleNamespace(data={"character_bar_visible": False})
        bar.parent_root = SimpleNamespace(after=Mock())
        bar.update_card_states = Mock()

        bar.poll_active_window()

        bar.update_card_states.assert_not_called()
        bar.parent_root.after.assert_called_once_with(250, bar.poll_active_window)

    def test_compact_mode_restores_an_enabled_bar_without_retoggle(self):
        bar = CharacterQuickBar.__new__(CharacterQuickBar)
        bar.config = SimpleNamespace(data={"character_bar_visible": True})
        bar.parent_root = SimpleNamespace(after_idle=Mock(), after=Mock())
        bar._layout_transition_token = 4
        bar._pending_signature = ("stale",)
        bar._transitioning = True
        bar.refresh_layout_immediately = Mock()
        bar.set_visible = Mock()

        bar.restore_after_presentation_change()

        self.assertEqual(bar._layout_transition_token, 5)
        self.assertIsNone(bar._pending_signature)
        self.assertFalse(bar._transitioning)
        bar.refresh_layout_immediately.assert_called_once_with()
        bar.parent_root.after_idle.assert_called_once()
        bar.parent_root.after.assert_called_once()

    def test_orientation_change_uses_atomic_visible_rebuild(self):
        bar = CharacterQuickBar.__new__(CharacterQuickBar)
        bar.var_vertical = Mock()
        bar.var_vertical.get.side_effect = [False, True]
        bar.config = SimpleNamespace(data={}, save=Mock(return_value=True))
        bar.restore_after_presentation_change = Mock()

        bar.toggle_orientation()

        bar.var_vertical.set.assert_called_once_with(True)
        self.assertTrue(bar.config.data["character_bar_vertical"])
        bar.restore_after_presentation_change.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
