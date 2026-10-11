import unittest

from streamdeck_model import (
    is_stateful_streamdeck_command,
    move_streamdeck_control,
    ordered_streamdeck_controls,
    remove_streamdeck_control,
)


class StreamdeckModelTests(unittest.TestCase):
    def profile(self):
        return {
            "microphone_source": "Mic/Aux",
            "camera_source": "Caméra",
            "camera_scene": "CAM",
            "pause_scene": "Pause",
            "custom_controls": [{
                "id": "custom-web", "label": "WEB", "icon_id": "web",
                "command": "switch_scene", "scene": "Internet", "source": "",
            }],
            "streamdeck_order": ["microphone", "camera", "pause", "custom-web"],
            "streamdeck_hidden_controls": [],
        }

    def test_simple_scene_alias_is_not_stateful(self):
        self.assertFalse(is_stateful_streamdeck_command("switch_scene"))
        self.assertTrue(is_stateful_streamdeck_command("toggle_scene"))
        self.assertTrue(is_stateful_streamdeck_command("toggle_microphone"))

    def test_native_and_custom_controls_share_one_order(self):
        profile = self.profile()
        self.assertTrue(move_streamdeck_control(profile, "custom-web", -1))
        self.assertEqual(
            [item["id"] for item in ordered_streamdeck_controls(profile)],
            ["microphone", "camera", "custom-web", "pause"],
        )

    def test_native_control_can_be_removed_without_losing_obs_settings(self):
        profile = self.profile()
        remove_streamdeck_control(profile, "camera")
        self.assertEqual(
            [item["id"] for item in ordered_streamdeck_controls(profile)],
            ["microphone", "pause", "custom-web"],
        )
        self.assertEqual(profile["camera_source"], "Caméra")
        self.assertIn("camera", profile["streamdeck_hidden_controls"])

    def test_custom_control_is_deleted(self):
        profile = self.profile()
        remove_streamdeck_control(profile, "custom-web")
        self.assertEqual(profile["custom_controls"], [])
        self.assertNotIn("custom-web", profile["streamdeck_order"])


if __name__ == "__main__":
    unittest.main()
