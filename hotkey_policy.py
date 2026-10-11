"""Shared validation rules for DOSOFT global shortcuts."""

from __future__ import annotations

from copy import deepcopy


CORE_BINDINGS = (
    ("prev_key", "Personnage précédent"),
    ("next_key", "Personnage suivant"),
    ("leader_key", "Chef"),
    ("toggle_app_key", "Afficher/cacher DOSOFT"),
    ("refresh_key", "Actualiser"),
    ("quit_key", "Quitter DOSOFT"),
    ("radial_menu_hotkey", "Roue radiale"),
    ("team_switch_key", "Changer d’équipe"),
)

_MODIFIER_ALIASES = {
    "control": "ctrl", "left ctrl": "ctrl", "right ctrl": "ctrl",
    "menu": "alt", "left alt": "alt", "right alt": "alt", "alt gr": "alt",
    "maj": "shift", "left shift": "shift", "right shift": "shift",
}
_MODIFIER_ORDER = ("ctrl", "alt", "shift")


def normalize_hotkey(value):
    """Normalize casing, aliases and modifier order without changing the key."""
    parts = [part.strip().casefold() for part in str(value or "").split("+") if part.strip()]
    if not parts:
        return ""
    parts = [_MODIFIER_ALIASES.get(part, part) for part in parts]
    modifiers = [name for name in _MODIFIER_ORDER if name in parts]
    keys = [part for part in parts if part not in _MODIFIER_ORDER]
    return "+".join(modifiers + keys)


def hotkey_bindings(settings):
    """Yield active ``(identifier, label, normalized shortcut)`` bindings."""
    for key, label in CORE_BINDINGS:
        if key == "radial_menu_hotkey" and not settings.get("radial_menu_active", True):
            continue
        if key == "team_switch_key" and settings.get("fast_switch_team_disabled", False):
            continue
        value = normalize_hotkey(settings.get(key, ""))
        if value:
            yield key, label, value

    mode = settings.get("advanced_bind_mode", "cycle")
    if mode == "cycle":
        for index, raw in enumerate(settings.get("cycle_row_binds", [])):
            value = normalize_hotkey(raw)
            if value:
                yield f"cycle_row_binds:{index}", f"Ligne {index + 1}", value
    elif mode == "bind":
        for pseudo, raw in settings.get("persistent_character_binds", {}).items():
            value = normalize_hotkey(raw)
            if value:
                yield f"persistent_character_binds:{pseudo}", f"Personnage {pseudo}", value


def find_hotkey_conflicts(settings):
    grouped = {}
    for identifier, label, value in hotkey_bindings(settings):
        grouped.setdefault(value, []).append((identifier, label))
    return {
        value: entries for value, entries in grouped.items() if len(entries) > 1
    }


def assignment_conflict(settings, identifier, value):
    """Return the first conflicting label for a proposed core assignment."""
    normalized = normalize_hotkey(value)
    if not normalized:
        return None
    for other_identifier, label, other_value in hotkey_bindings(settings):
        if other_identifier != identifier and other_value == normalized:
            return label
    return None


def describe_conflicts(conflicts):
    lines = []
    for value, entries in sorted(conflicts.items()):
        labels = " / ".join(label for _identifier, label in entries)
        lines.append(f"{value.upper()} : {labels}")
    return "\n".join(lines)


def candidate_with_assignment(settings, identifier, value):
    candidate = deepcopy(settings)
    candidate[identifier] = normalize_hotkey(value)
    return candidate
