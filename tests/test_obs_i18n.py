import json
from pathlib import Path
import string
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "resources" / "i18n"


class ObsTranslationsTests(unittest.TestCase):
    def test_obs_and_streamdeck_keys_exist_in_every_locale(self):
        required = {
            "obs_assistant_title",
            "obs_connected_ready",
            "obs_emergency_confirm",
            "obs_error_connection",
            "obs_status_connected",
            "streamdeck_action_switch_scene",
            "streamdeck_layout",
            "streamdeck_title",
        }
        for locale in ("fr", "en", "es", "pt", "de"):
            with self.subTest(locale=locale):
                data = json.loads((LOCALES / f"{locale}.yml").read_text(encoding="utf-8-sig"))
                self.assertTrue(required.issubset(data))

    def test_assistant_title_is_really_translated(self):
        values = {
            locale: json.loads((LOCALES / f"{locale}.yml").read_text(encoding="utf-8-sig"))["obs_assistant_title"]
            for locale in ("fr", "en", "es", "pt", "de")
        }
        self.assertEqual(5, len(set(values.values())))

    def test_every_locale_has_the_same_complete_catalog(self):
        catalogs = {
            locale: json.loads((LOCALES / f"{locale}.yml").read_text(encoding="utf-8-sig"))
            for locale in ("fr", "en", "es", "pt", "de")
        }
        reference = set(catalogs["fr"])
        for locale, catalog in catalogs.items():
            with self.subTest(locale=locale):
                self.assertEqual(reference, set(catalog))

    def test_placeholders_match_french_reference(self):
        catalogs = {
            locale: json.loads((LOCALES / f"{locale}.yml").read_text(encoding="utf-8-sig"))
            for locale in ("fr", "en", "es", "pt", "de")
        }
        formatter = string.Formatter()
        for key, reference_text in catalogs["fr"].items():
            reference_fields = {name for _literal, name, _spec, _conversion in formatter.parse(reference_text) if name}
            for locale, catalog in catalogs.items():
                with self.subTest(key=key, locale=locale):
                    fields = {name for _literal, name, _spec, _conversion in formatter.parse(catalog[key]) if name}
                    self.assertEqual(reference_fields, fields)


if __name__ == "__main__":
    unittest.main()
