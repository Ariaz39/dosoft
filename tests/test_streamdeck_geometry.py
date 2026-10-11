import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from obs_stream_dock import ObsStreamDock


class StreamdeckGeometryTests(unittest.TestCase):
    def test_position_is_clamped_inside_monitor_work_area(self):
        position = ObsStreamDock.clamp_to_work_areas(
            (2500, 1800), (100, 200), [(0, 0, 1920, 1040)]
        )
        self.assertEqual(position, (1812, 832))

    def test_position_uses_monitor_containing_dock_center(self):
        position = ObsStreamDock.clamp_to_work_areas(
            (2100, 900), (80, 120), [(0, 0, 1920, 1040), (1920, 0, 3840, 1040)]
        )
        self.assertEqual(position, (2100, 900))

    def test_gap_between_monitors_recovers_to_nearest_monitor(self):
        position = ObsStreamDock.clamp_to_work_areas(
            (1950, 1200), (80, 120), [(0, 0, 1920, 1040), (1920, -1080, 3840, 0)]
        )
        self.assertEqual(position, (1832, 912))

    def test_watchdog_does_not_recover_a_native_visible_dock(self):
        dock = ObsStreamDock.__new__(ObsStreamDock)
        dock.bridge = SimpleNamespace(
            enabled=True,
            profile=SimpleNamespace(data={"dock_enabled": True}),
            _record=Mock(),
        )
        dock.is_natively_visible = Mock(return_value=True)
        dock.show_and_recover = Mock()
        dock._refresh_control_states = Mock()
        dock.after = Mock()
        dock._periodic_state_refresh()
        dock.show_and_recover.assert_not_called()
        dock.after.assert_called_once_with(3000, dock._periodic_state_refresh)

    def test_watchdog_never_manipulates_an_invisible_native_window(self):
        dock = ObsStreamDock.__new__(ObsStreamDock)
        dock.bridge = SimpleNamespace(
            enabled=True,
            profile=SimpleNamespace(data={"dock_enabled": True}),
            _record=Mock(),
        )
        dock.is_natively_visible = Mock(return_value=False)
        dock.show_and_recover = Mock()
        dock._refresh_control_states = Mock()
        dock.after = Mock()
        dock._periodic_state_refresh()
        dock.show_and_recover.assert_not_called()
        dock.after.assert_called_once_with(3000, dock._periodic_state_refresh)

    def test_only_latest_rebuild_can_fit_and_show_the_dock(self):
        dock = ObsStreamDock.__new__(ObsStreamDock)
        dock._rebuild_generation = 7
        dock.bridge = SimpleNamespace(
            profile=SimpleNamespace(data={"dock_enabled": True}),
        )
        dock.fit_and_position_window = Mock()
        dock.show_and_recover = Mock()

        dock.finish_rebuild(6)
        dock.fit_and_position_window.assert_not_called()

        dock.finish_rebuild(7)
        dock.fit_and_position_window.assert_called_once_with()
        dock.show_and_recover.assert_called_once_with(fit=False)


if __name__ == "__main__":
    unittest.main()
