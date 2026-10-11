import unittest

from compatibility import compatibility_warnings, numeric_version


class CompatibilityTests(unittest.TestCase):
    def test_numeric_version_accepts_obs_suffix(self):
        self.assertEqual(numeric_version("32.0.0-beta2"), (32, 0, 0))

    def test_untested_obs_warns_without_blocking(self):
        warnings = compatibility_warnings(
            "0.3.0", "33.0.1",
            {"plugin_recommended": "0.3.0", "obs_tested_majors": [32]},
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("pas encore validé", warnings[0])

    def test_older_plugin_has_explicit_manual_update_message(self):
        warnings = compatibility_warnings(
            "0.2.0", "32.0.0",
            {"plugin_recommended": "0.3.0", "obs_tested_majors": [32]},
        )
        self.assertIn("setup DOSOFT", warnings[0])


if __name__ == "__main__":
    unittest.main()
