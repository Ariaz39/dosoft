import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from main import OrganizerApp


class TeamSwitchTests(unittest.TestCase):
    def make_app(self, current_mode="Team 1"):
        app = OrganizerApp.__new__(OrganizerApp)
        app.config = SimpleNamespace(data={"current_mode": current_mode, "game_version": "Unity"})
        app.logic = Mock()
        app.logic.all_accounts = [
            {"name": "A", "hwnd": 11, "active": True, "team": "Team 1"},
            {"name": "B", "hwnd": 22, "active": True, "team": "Team 2"},
        ]

        def set_mode(team):
            app.config.data["current_mode"] = team

        app.logic.set_mode.side_effect = set_mode
        app.logic.get_cycle_list.side_effect = lambda: [
            account for account in app.logic.all_accounts
            if app.config.data["current_mode"] == "ALL"
            or account["team"] == app.config.data["current_mode"]
        ]
        app.gui = SimpleNamespace(combo_mode=Mock(), root=Mock())
        app.character_bar = Mock()
        app.current_idx = 0
        return app

    def test_fast_switch_toggles_only_the_two_teams(self):
        app = self.make_app("Team 1")
        app.gui.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        app.switch_team_mode()
        self.assertEqual(app.config.data["current_mode"], "Team 2")
        app.switch_team_mode()
        self.assertEqual(app.config.data["current_mode"], "Team 1")

    def test_team_change_updates_bar_without_rebuilding_main_rows(self):
        app = self.make_app()
        with patch("main.win32gui.GetForegroundWindow", return_value=22):
            self.assertTrue(app.set_team_mode("Team 2"))
        app.gui.combo_mode.set.assert_called_once_with("Team 2")
        app.character_bar.update_accounts.assert_called_once_with(
            app.logic.all_accounts, "Unity", immediate=True
        )
        self.assertEqual(app.current_idx, 0)

    def test_cycle_uses_real_foreground_after_team_change(self):
        app = self.make_app("ALL")
        app.logic.focus_window = Mock()
        with patch("main.win32gui.GetForegroundWindow", return_value=11):
            app._apply_cycle_step(1)
        app.logic.focus_window.assert_called_once_with(22)


if __name__ == "__main__":
    unittest.main()
