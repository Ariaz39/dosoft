"""Fail closed when a DOSOFT release is incomplete or internally inconsistent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import string
import sys


LOCALES = ("fr", "en", "es", "pt", "de")


def fail(message):
    print(f"[ERREUR] {message}", file=sys.stderr)
    raise SystemExit(1)


def placeholders(value):
    return {
        field
        for _literal, field, _format_spec, _conversion in string.Formatter().parse(value)
        if field
    }


def validate_source(root):
    version_data = json.loads((root / "version.json").read_text(encoding="utf-8-sig"))
    version = str(version_data.get("version", "")).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"version.json contient une version invalide : {version!r}")

    app_version_text = (root / "app_version.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', app_version_text, re.MULTILINE)
    if not match or match.group(1) != version:
        fail("app_version.py et version.json ne portent pas la même version")

    compatibility = json.loads((root / "resources" / "compatibility.json").read_text(encoding="utf-8-sig"))
    if compatibility.get("dosoft_version") != version:
        fail("resources/compatibility.json ne correspond pas à la version DOSOFT")
    if compatibility.get("plugin_recommended") != version_data.get("plugin_version"):
        fail("version.json et compatibility.json ne recommandent pas le même plugin OBS")

    catalogs = {
        locale: json.loads((root / "resources" / "i18n" / f"{locale}.yml").read_text(encoding="utf-8-sig"))
        for locale in LOCALES
    }
    reference_keys = set(catalogs["fr"])
    for locale, catalog in catalogs.items():
        if set(catalog) != reference_keys:
            missing = sorted(reference_keys - set(catalog))
            extra = sorted(set(catalog) - reference_keys)
            fail(f"catalogue {locale} incohérent, absentes={missing}, supplémentaires={extra}")
        for key, french_value in catalogs["fr"].items():
            if placeholders(catalog[key]) != placeholders(french_value):
                fail(f"variables de traduction incompatibles pour {locale}:{key}")

    required = (
        root / "logo.ico",
        root / "LICENSE",
        root / "THIRD_PARTY_NOTICES.md",
        root / "resources" / "skin" / "obs" / "obs-logo.png",
        root / "resources" / "skin" / "streamdeck" / "icons" / "ATTRIBUTION.txt",
        root / "obs-plugin" / "dofus-scene-guard.dll",
    )
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"ressource de release absente ou vide : {path.relative_to(root)}")
    return version


def validate_executable(root, executable):
    if not executable.is_file():
        fail(f"exécutable absent : {executable}")
    if executable.stat().st_size < 5_000_000:
        fail(f"exécutable anormalement petit : {executable.stat().st_size} octets")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--executable", type=Path)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    version = validate_source(root)
    if arguments.executable:
        validate_executable(root, arguments.executable.resolve())
    print(f"[OK] DOSOFT {version} : sources et ressources de release cohérentes")


if __name__ == "__main__":
    main()
