import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from config_manager import Config, default_settings_path


class ConfigPersistenceTests(unittest.TestCase):
    def test_default_path_is_per_windows_user(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"APPDATA": directory}, clear=False
        ):
            self.assertEqual(
                default_settings_path(), Path(directory) / "DOSOFT" / "settings.json"
            )

    def test_legacy_settings_are_migrated_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "old" / "settings.json"
            target = root / "new" / "settings.json"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps({"leader_name": "Testeur"}), encoding="utf-8")

            config = Config(target, legacy_paths=[legacy])

            self.assertEqual(config.data["leader_name"], "Testeur")
            self.assertTrue(target.exists())
            self.assertIn("déplacés", config.recovery_notice)
            self.assertTrue(legacy.exists())

    def test_corrupt_current_file_recovers_valid_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            config = Config(path, legacy_paths=[])
            config.data["leader_name"] = "Sauvegardé"
            self.assertTrue(config.save())
            config.data["leader_name"] = "Nouveau"
            self.assertTrue(config.save())
            path.write_text("{fichier cassé", encoding="utf-8")

            recovered = Config(path, legacy_paths=[])

            self.assertEqual(recovered.data["leader_name"], "Sauvegardé")
            self.assertIn("restaurée", recovered.recovery_notice)
            self.assertTrue(list(path.parent.glob("settings.corrupt-*.json")))

    def test_reset_writes_valid_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            config = Config(path, legacy_paths=[])
            config.data["leader_name"] = "À effacer"
            config.save()
            self.assertTrue(config.reset_settings())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["leader_name"], "")

    def test_former_default_f12_becomes_hide_ui_without_quitting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({
                "toggle_app_key": "f10",
                "quit_key": "f12",
            }), encoding="utf-8")

            config = Config(path, legacy_paths=[])

            self.assertEqual(config.data["toggle_app_key"], "f12")
            self.assertEqual(config.data["quit_key"], "")
            self.assertTrue(config.data["hide_ui_f12_1_3_8"])

    def test_fast_switch_is_forced_off_while_feature_is_withdrawn(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({
                "fast_switch_team_disabled": False,
                "team_switch_key": "ctrl+t",
            }), encoding="utf-8")

            config = Config(path, legacy_paths=[])

            self.assertTrue(config.data["fast_switch_team_disabled"])
            self.assertEqual(config.data["team_switch_key"], "ctrl+t")

    def test_save_failure_is_reported_to_registered_handler(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(Path(directory) / "settings.json", legacy_paths=[])
            handler = Mock()
            config.error_handler = handler

            with patch.object(Path, "write_text", side_effect=OSError("disque verrouillé")):
                self.assertFalse(config.save())

            handler.assert_called_once()
            self.assertIn("disque verrouillé", handler.call_args.args[0])

    def test_concurrent_saves_use_one_serialized_atomic_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            config = Config(path, legacy_paths=[])
            results = []

            threads = [threading.Thread(target=lambda: results.append(config.save())) for _ in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(results, [True] * 12)
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)
            self.assertFalse(list(path.parent.glob("settings.json.*.tmp")))

    def test_transient_permission_error_is_retried_without_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(Path(directory) / "settings.json", legacy_paths=[])
            handler = Mock()
            config.error_handler = handler
            original_write_text = Path.write_text
            attempts = 0

            def locked_twice(target, *args, **kwargs):
                nonlocal attempts
                if str(target).endswith(".tmp") and attempts < 2:
                    attempts += 1
                    raise PermissionError(13, "fichier temporairement verrouillé")
                return original_write_text(target, *args, **kwargs)

            with patch.object(Path, "write_text", locked_twice):
                self.assertTrue(config.save())

            self.assertEqual(attempts, 2)
            handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
