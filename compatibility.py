"""Local compatibility manifest; it never downloads or installs updates."""

import json
import re

from resource_paths import resource_path


DEFAULT_COMPATIBILITY = {
    "schema_version": 1,
    "dosoft_version": "1.3.8",
    "plugin_recommended": "0.3.1",
    "protocol_min": 2,
    "protocol_max": 3,
    "obs_tested_majors": [32],
    "manual_update_url": "https://dosoft.fr",
}


def load_compatibility_manifest():
    try:
        with open(resource_path("resources", "compatibility.json"), "r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError("manifest root")
        result = dict(DEFAULT_COMPATIBILITY)
        result.update(loaded)
        return result
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return dict(DEFAULT_COMPATIBILITY)


def numeric_version(value):
    """Parse the numeric prefix of a semantic version without trusting labels."""
    match = re.match(r"^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(value or ""))
    if not match:
        return ()
    return tuple(int(part or 0) for part in match.groups())


def compatibility_warnings(plugin_version="", obs_version="", manifest=None, translator=None):
    """Return warnings while keeping otherwise compatible features usable."""
    manifest = manifest or load_compatibility_manifest()
    def translated(key, default, **values):
        text = translator(key, default) if translator else default
        try:
            return text.format(**values)
        except (KeyError, ValueError, IndexError):
            return text

    warnings = []
    plugin = numeric_version(plugin_version)
    recommended = numeric_version(manifest.get("plugin_recommended"))
    if plugin and recommended and plugin < recommended:
        warnings.append(translated(
            "obs_warning_plugin_old",
            "Plugin OBS {current} ancien : installez la version {recommended} avec le setup DOSOFT.",
            current=plugin_version, recommended=manifest["plugin_recommended"],
        ))
    obs = numeric_version(obs_version)
    tested = {int(value) for value in manifest.get("obs_tested_majors", [])}
    if obs and obs[0] not in tested:
        warnings.append(translated(
            "obs_warning_obs_untested",
            "OBS {version} n’est pas encore validé avec ce connecteur. Vos scènes restent conservées, mais testez la capture avant un direct.",
            version=obs_version,
        ))
    return warnings
