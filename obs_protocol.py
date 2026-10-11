"""Versioned contract shared by DOSOFT and the OBS Scene Guard bridge."""

from __future__ import annotations


PROTOCOL_VERSION = 3
PROTOCOL_MINIMUM = 2
CLIENT_NAME = "DOSOFT"
CLIENT_VERSION = "1.3.8"

LEGACY_CAPABILITIES = frozenset({
    "inventory", "setup_scenes", "sync_team", "rebuild_team",
    "account_selection", "auto_swap", "obs_control", "multi_engine",
    "cursor_capture", "fallback_scene",
})

EVENT_CAPABILITIES = {
    "hello": "inventory",
    "get_inventory": "inventory",
    "setup_scenes": "setup_scenes",
    "sync_team": "sync_team",
    "rebuild_team": "rebuild_team",
    "dofus_account_selected": "account_selection",
    "set_auto_swap": "auto_swap",
    "obs_control": "obs_control",
    "obs_control_state": "obs_control_state",
    "deactivate": "auto_swap",
}


def prepare_request(payload):
    request = dict(payload)
    request["version"] = PROTOCOL_VERSION
    request.setdefault("client", {"name": CLIENT_NAME, "version": CLIENT_VERSION})
    return request


def validate_response(response, request_id):
    if not isinstance(response, dict):
        return "invalid_response"
    version = response.get("version")
    if not isinstance(version, int) or not PROTOCOL_MINIMUM <= version <= PROTOCOL_VERSION:
        return "unsupported_protocol"
    response_id = response.get("request_id")
    if request_id and response_id != request_id:
        return "request_id_mismatch"
    return ""


def negotiate_plugin(response):
    """Return normalized plugin metadata, accepting the existing 0.2 bridge."""
    error = validate_response(response, response.get("request_id", ""))
    if error:
        return {"compatible": False, "error": error}
    data = response.get("data") or {}
    plugin_protocol = data.get("protocol_version", response.get("version"))
    plugin_minimum = data.get("protocol_min", PROTOCOL_MINIMUM)
    if not isinstance(plugin_protocol, int) or not isinstance(plugin_minimum, int):
        return {"compatible": False, "error": "invalid_handshake"}
    if plugin_protocol < PROTOCOL_MINIMUM or plugin_minimum > PROTOCOL_VERSION:
        return {"compatible": False, "error": "unsupported_protocol"}

    advertised = data.get("capabilities")
    legacy = not isinstance(advertised, list)
    capabilities = LEGACY_CAPABILITIES if legacy else frozenset(
        str(value) for value in advertised if value
    )
    return {
        "compatible": True,
        "legacy": legacy,
        "plugin_version": str(data.get("plugin_version") or "inconnue"),
        "protocol_version": plugin_protocol,
        "capabilities": capabilities,
        "session_id": str(data.get("session_id") or ""),
        "obs_version": str(data.get("obs_version") or ""),
    }


def required_capability(event):
    return EVENT_CAPABILITIES.get(str(event or ""), "")


def should_resynchronize(previous_session, current_session, was_connected, legacy=False):
    """Decide whether a successful health check must rebuild live OBS state."""
    if not was_connected or legacy:
        return True
    return bool(previous_session and current_session and previous_session != current_session)
