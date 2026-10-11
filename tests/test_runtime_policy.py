import unittest

from runtime_policy import should_run_retro_autofocus


class RuntimePolicyTests(unittest.TestCase):
    def test_retro_autofocus_requires_engine_and_explicit_activation(self):
        self.assertFalse(should_run_retro_autofocus({"game_version": "Unity", "auto_focus_retro": True}))
        self.assertFalse(should_run_retro_autofocus({"game_version": "Rétro", "auto_focus_retro": False}))
        self.assertTrue(should_run_retro_autofocus({"game_version": "Rétro", "auto_focus_retro": True}))


if __name__ == "__main__":
    unittest.main()
