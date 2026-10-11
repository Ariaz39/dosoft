from types import SimpleNamespace
import unittest

from obs_stream_dock import ObsStreamDock


class DummyProfile:
    def __init__(self):
        self.data = {"dock_states": {}}
        self.saves = 0

    def save(self):
        self.saves += 1


def make_dock(command, state=False):
    dock = ObsStreamDock.__new__(ObsStreamDock)
    dock.states = {"button": state}
    dock.control_commands = {"button": command}
    dock.bridge = SimpleNamespace(profile=DummyProfile())
    dock.applied = []
    dock.apply_state = dock.applied.append
    return dock


class StreamdeckStateTests(unittest.TestCase):
    def test_plugin_state_replaces_stale_local_state(self):
        dock = make_dock("toggle_microphone", state=True)
        dock._apply_control_response(
            "button", {"ok": True, "data": {"stateful": True, "off": False}}, False
        )
        self.assertFalse(dock.states["button"])
        self.assertEqual(dock.bridge.profile.saves, 0)

    def test_direct_scene_alias_never_latches(self):
        dock = make_dock("switch_scene", state=True)
        dock._apply_control_response(
            "button", {"ok": True, "data": {"stateful": False, "off": False}}, True
        )
        self.assertNotIn("button", dock.states)

    def test_legacy_toggle_response_keeps_compatibility(self):
        dock = make_dock("toggle_camera", state=False)
        dock._apply_control_response("button", {"ok": True}, True)
        self.assertTrue(dock.states["button"])
        self.assertEqual(dock.bridge.profile.saves, 1)


if __name__ == "__main__":
    unittest.main()
