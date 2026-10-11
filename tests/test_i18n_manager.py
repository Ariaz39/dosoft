import tempfile
from pathlib import Path
import unittest

from i18n_manager import I18nManager, LANGUAGE_NAMES, SUPPORTED_LOCALES


class I18nManagerTests(unittest.TestCase):
    def test_five_languages_are_available_in_settings_order(self):
        self.assertEqual(("fr", "en", "es", "pt", "de"), SUPPORTED_LOCALES)
        self.assertEqual(set(SUPPORTED_LOCALES), set(LANGUAGE_NAMES))

    def test_unknown_locale_falls_back_to_french(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "fr.yml").write_text('{"hello": "Bonjour"}', encoding="utf-8")
            manager = I18nManager("unknown", directory)
            self.assertEqual("fr", manager.locale)
            self.assertEqual("Bonjour", manager.t("hello"))


if __name__ == "__main__":
    unittest.main()
