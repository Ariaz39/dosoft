import unittest

from hotkey_policy import (
    assignment_conflict,
    find_hotkey_conflicts,
    normalize_hotkey,
)


class HotkeyPolicyTests(unittest.TestCase):
    def test_normalize_hotkey_is_case_and_modifier_order_independent(self):
        self.assertEqual(normalize_hotkey(" Shift + CTRL + F1 "), "ctrl+shift+f1")
        self.assertEqual(normalize_hotkey("MAJ+A"), "shift+a")

    def test_core_and_advanced_conflict_is_detected(self):
        settings = {
            "toggle_app_key": "F12",
            "advanced_bind_mode": "cycle",
            "cycle_row_binds": ["f12"],
        }
        conflicts = find_hotkey_conflicts(settings)
        self.assertIn("f12", conflicts)

    def test_assignment_reports_existing_action_without_mutating_settings(self):
        settings = {"prev_key": "tab", "next_key": "²"}
        self.assertEqual(assignment_conflict(settings, "next_key", "TAB"), "Personnage précédent")
        self.assertEqual(settings["next_key"], "²")

    def test_inactive_advanced_mode_does_not_create_false_conflict(self):
        settings = {
            "prev_key": "tab",
            "advanced_bind_mode": "bind",
            "cycle_row_binds": ["tab"],
            "persistent_character_binds": {},
        }
        self.assertEqual(find_hotkey_conflicts(settings), {})

    def test_disabled_optional_controls_do_not_reserve_shortcuts(self):
        settings = {
            "prev_key": "tab",
            "radial_menu_active": False,
            "radial_menu_hotkey": "tab",
            "fast_switch_team_disabled": True,
            "team_switch_key": "tab",
        }
        self.assertEqual(find_hotkey_conflicts(settings), {})


if __name__ == "__main__":
    unittest.main()
