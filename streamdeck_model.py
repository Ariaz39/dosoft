"""Pure helpers for the configurable OBS Streamdeck."""

BUILTIN_STREAMDECK_IDS = ("microphone", "camera", "pause")

STATEFUL_STREAMDECK_COMMANDS = frozenset({
    "toggle_microphone",
    "toggle_camera",
    "toggle_pause",
    "toggle_scene",
    "toggle_source",
})


def is_stateful_streamdeck_command(command):
    """Return whether a successful click represents a persistent on/off state."""
    return str(command) in STATEFUL_STREAMDECK_COMMANDS


def builtin_streamdeck_controls(profile):
    """Build native controls while resolving their current OBS profile targets."""
    return [
        {
            "id": "microphone", "label": "MIC", "icon_id": "microphone",
            "command": "toggle_microphone",
            "source": str(profile.get("microphone_source", "")), "scene": "",
            "builtin": True,
        },
        {
            "id": "camera", "label": "CAM", "icon_id": "camera",
            "command": "toggle_camera",
            "source": str(profile.get("camera_source", "")),
            "scene": str(profile.get("camera_scene", "")),
            "builtin": True,
        },
        {
            "id": "pause", "label": "PAUSE", "icon_id": "pause",
            "command": "toggle_pause", "source": "",
            "scene": str(profile.get("pause_scene", "")),
            "builtin": True,
        },
    ]


def ordered_streamdeck_controls(profile):
    """Return visible native and custom controls in the user's saved order."""
    controls = builtin_streamdeck_controls(profile)
    controls.extend(
        item for item in profile.get("custom_controls", [])
        if isinstance(item, dict) and item.get("id") and item.get("command")
    )
    by_id = {str(item["id"]): item for item in controls}
    hidden = {
        str(item) for item in profile.get("streamdeck_hidden_controls", [])
        if str(item) in BUILTIN_STREAMDECK_IDS
    }
    order = []
    for item in profile.get("streamdeck_order", []):
        control_id = str(item)
        if control_id in by_id and control_id not in hidden and control_id not in order:
            order.append(control_id)
    for control_id in by_id:
        if control_id not in hidden and control_id not in order:
            order.append(control_id)
    return [by_id[control_id] for control_id in order]


def normalize_streamdeck_profile(profile):
    """Repair ordering metadata without resurrecting deleted native controls."""
    before_order = list(profile.get("streamdeck_order", []))
    before_hidden = list(profile.get("streamdeck_hidden_controls", []))
    visible_ids = [item["id"] for item in ordered_streamdeck_controls(profile)]
    profile["streamdeck_order"] = visible_ids
    profile["streamdeck_hidden_controls"] = [
        item for item in BUILTIN_STREAMDECK_IDS if item in before_hidden
    ]
    return before_order != visible_ids or before_hidden != profile["streamdeck_hidden_controls"]


def remove_streamdeck_control(profile, control_id):
    """Remove a native control from the dock or delete a custom control."""
    control_id = str(control_id)
    if control_id in BUILTIN_STREAMDECK_IDS:
        hidden = profile.setdefault("streamdeck_hidden_controls", [])
        if control_id not in hidden:
            hidden.append(control_id)
    else:
        profile["custom_controls"] = [
            item for item in profile.get("custom_controls", [])
            if str(item.get("id", "")) != control_id
        ]
    profile["streamdeck_order"] = [
        item for item in profile.get("streamdeck_order", []) if str(item) != control_id
    ]


def move_streamdeck_control(profile, control_id, direction):
    """Move one visible control by one slot and return whether it moved."""
    order = [item["id"] for item in ordered_streamdeck_controls(profile)]
    try:
        index = order.index(str(control_id))
    except ValueError:
        return False
    target = index + int(direction)
    if target < 0 or target >= len(order):
        return False
    order[index], order[target] = order[target], order[index]
    profile["streamdeck_order"] = order
    return True
