import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dosoft_obs_bridge import ObsProfile


class ObsProfileTests(unittest.TestCase):
    def test_v2_profile_migrates_native_and_custom_streamdeck_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obs_profile.json"
            path.write_text(json.dumps({
                "version": 2,
                "custom_controls": [{
                    "id": "custom-web", "command": "switch_scene", "scene": "Internet",
                }],
            }), encoding="utf-8")

            profile = ObsProfile(path)

            self.assertEqual(profile.data["version"], 3)
            self.assertEqual(
                profile.data["streamdeck_order"],
                ["microphone", "camera", "pause", "custom-web"],
            )
            self.assertEqual(profile.data["streamdeck_hidden_controls"], [])

    def test_three_managed_scene_names_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obs_profile.json"
            path.write_text(json.dumps({
                "version": 2,
                "game_scene": "Jeu_Wakfu",
                "retro_game_scene": "Jeu_Dofus_Rétro",
                "wakfu_game_scene": "Jeu_Wakfu",
            }), encoding="utf-8")

            profile = ObsProfile(path)

            names = [
                profile.data["game_scene"],
                profile.data["retro_game_scene"],
                profile.data["wakfu_game_scene"],
            ]
            self.assertEqual(names, ["Jeu_Dofus_Unity", "Jeu_Dofus_Rétro", "Jeu_Wakfu"])
            self.assertEqual(len({name.casefold() for name in names}), 3)

    def test_failed_profile_write_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obs_profile.json"
            path.write_text('{"version": 2, "stream_scene": "Avant"}', encoding="utf-8")
            profile = ObsProfile(path)
            profile.data["stream_scene"] = "Après"

            original_write_text = Path.write_text

            def fail_temporary(target, *args, **kwargs):
                if str(target).endswith(".tmp"):
                    raise OSError("disque verrouillé")
                return original_write_text(target, *args, **kwargs)

            with patch.object(Path, "write_text", fail_temporary):
                self.assertFalse(profile.save())

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["stream_scene"], "Avant")
            self.assertIn("disque verrouillé", profile.last_error)

    def test_corrupt_profile_recovers_from_last_valid_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obs_profile.json"
            backup = Path(directory) / "obs_profile.backup.json"
            path.write_text("{broken", encoding="utf-8")
            backup.write_text(json.dumps({
                "version": 3,
                "stream_scene": "Mon Stream",
            }), encoding="utf-8")

            profile = ObsProfile(path)

            self.assertTrue(profile.exists)
            self.assertEqual(profile.data["stream_scene"], "Mon Stream")
            self.assertIn("restauré", profile.recovery_notice)
            self.assertTrue(list(Path(directory).glob("obs_profile.corrupt-*.json")))


if __name__ == "__main__":
    unittest.main()
