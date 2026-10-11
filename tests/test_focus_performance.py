import unittest
from unittest.mock import patch

from logic import DofusLogic


class DummyConfig:
    def __init__(self, game_version="Unity"):
        self.data = {"game_version": game_version}


class FocusIdentityTests(unittest.TestCase):
    def test_same_unity_character_needs_no_global_rescan(self):
        logic = DofusLogic(DummyConfig())
        logic.all_accounts = [{"hwnd": 42, "name": "Personnage-Test", "is_menu": False}]
        with patch("logic.win32gui.GetWindowText", return_value="Personnage-Test - Cra"), patch.object(
            logic, "matches_current_game_window", return_value=True
        ):
            self.assertFalse(logic.focused_account_identity_changed(42))

    def test_renamed_unity_character_requests_one_refresh(self):
        logic = DofusLogic(DummyConfig())
        logic.all_accounts = [{"hwnd": 42, "name": "Ancien", "is_menu": False}]
        with patch("logic.win32gui.GetWindowText", return_value="Nouveau - Cra"), patch.object(
            logic, "matches_current_game_window", return_value=True
        ):
            self.assertTrue(logic.focused_account_identity_changed(42))

    def test_login_to_character_requests_refresh(self):
        logic = DofusLogic(DummyConfig())
        logic.all_accounts = [{"hwnd": 42, "name": "Menu Unity [U1]", "is_menu": True}]
        with patch("logic.win32gui.GetWindowText", return_value="Personnage-Test - Cra"), patch.object(
            logic, "matches_current_game_window", return_value=True
        ):
            self.assertTrue(logic.focused_account_identity_changed(42))


if __name__ == "__main__":
    unittest.main()
