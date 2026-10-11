from pathlib import Path
import tempfile
import unittest

from log_utils import append_rotating


class RotatingLogTests(unittest.TestCase):
    def test_log_is_rotated_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "debug.log"
            self.assertTrue(append_rotating(path, "première ligne", max_bytes=20, backup_count=2))
            self.assertTrue(append_rotating(path, "deuxième ligne longue", max_bytes=20, backup_count=2))

            self.assertTrue(path.exists())
            self.assertTrue(path.with_name("debug.log.1").exists())
            self.assertIn("deuxième", path.read_text(encoding="utf-8"))
            self.assertIn("première", path.with_name("debug.log.1").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
