import json
from pathlib import Path
import tempfile
import unittest

from release_backup import ensure_release_backup


class ReleaseBackupTests(unittest.TestCase):
    def test_new_version_snapshots_profiles_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            profile = root / "obs_profile.json"
            settings.write_text('{"language":"fr"}', encoding="utf-8")
            profile.write_text('{"version":3}', encoding="utf-8")

            backup = ensure_release_backup("1.3.8", root, (settings, profile))

            self.assertTrue((backup / "settings.json").exists())
            self.assertTrue((backup / "obs_profile.json").exists())
            self.assertIsNone(ensure_release_backup("1.3.8", root, (settings, profile)))
            self.assertEqual(
                json.loads((root / "release-state.json").read_text(encoding="utf-8"))["version"],
                "1.3.8",
            )


if __name__ == "__main__":
    unittest.main()
