from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from gui import ObsSettingsWindow


class ToggleValue:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StreamdeckSettingsTests(unittest.TestCase):
    def make_window(self, enabled, save_result=True):
        profile = SimpleNamespace(
            data={"dock_enabled": not enabled},
            save=Mock(return_value=save_result),
            last_error="écriture refusée",
        )
        app = SimpleNamespace(
            obs_bridge=SimpleNamespace(profile=profile),
            refresh_obs_stream_dock=Mock(),
            i18n=SimpleNamespace(t=lambda _key, default, **_kwargs: default),
        )
        window = ObsSettingsWindow.__new__(ObsSettingsWindow)
        window.app = app
        window.dock = ToggleValue(enabled)
        window.status = SimpleNamespace(configure=Mock())
        return window, profile

    def test_streamdeck_switch_is_saved_and_displayed_immediately(self):
        window, profile = self.make_window(True)

        self.assertTrue(window.toggle_streamdeck_immediately())

        self.assertTrue(profile.data["dock_enabled"])
        profile.save.assert_called_once_with()
        window.app.refresh_obs_stream_dock.assert_called_once_with()

    def test_streamdeck_switch_rolls_back_when_persistence_fails(self):
        window, profile = self.make_window(True, save_result=False)

        self.assertFalse(window.toggle_streamdeck_immediately())

        self.assertFalse(profile.data["dock_enabled"])
        self.assertFalse(window.dock.get())
        window.app.refresh_obs_stream_dock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
