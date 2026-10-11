"""Optional, local-only connection between DOSOFT and Dofus Scene Guard."""

import json
import os
import shutil
from collections import deque
from pathlib import Path
import threading
import time
import uuid
from datetime import datetime

import win32process
from compatibility import compatibility_warnings
from log_utils import append_rotating
from obs_protocol import (
    negotiate_plugin,
    prepare_request,
    required_capability,
    should_resynchronize,
    validate_response,
)
from streamdeck_model import BUILTIN_STREAMDECK_IDS, normalize_streamdeck_profile


PIPE_NAME = r"\\.\pipe\DofusSceneGuard"
APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "DOSOFT"
PROFILE_PATH = APP_DATA_DIR / "obs_profile.json"
LEGACY_PROFILE_PATH = Path(__file__).with_name("obs_profile.json")
PROFILE_VERSION = 3
PROFILE_DEFAULTS = {
    "version": PROFILE_VERSION,
    "stream_scene": "Stream",
    "game_scene": "Jeu_Dofus_Unity",
    "retro_game_scene": "Jeu_Dofus_Rétro",
    "wakfu_game_scene": "Jeu_Wakfu",
    "parent_scenes": ["Stream"],
    "fallback_enabled": False,
    "fallback_scene": "",
    "fallback_delay_ms": 2000,
    "pause_scene": "Pause",
    "microphone_source": "Mic/Aux",
    "camera_scene": "CAM",
    "camera_source": "Caméra",
    "capture_prefix": "DOSOFT Dofus — ",
    "retro_capture_prefix": "DOSOFT Retro — ",
    "wakfu_capture_prefix": "DOSOFT Wakfu — ",
    "max_captures": 12,
    "dock_enabled": False,
    "streamdeck_layout": "horizontal",
    "streamdeck_scale": 1.0,
    "streamdeck_order": list(BUILTIN_STREAMDECK_IDS),
    "streamdeck_hidden_controls": [],
    "diagnostics_enabled": False,
    "custom_controls": [],
}


class ObsProfile:
    """Persistent OBS extension profile, created only after explicit activation."""

    def __init__(self, path=PROFILE_PATH, translator=None):
        self.path = Path(path)
        self._translator = translator
        self.backup_path = self.path.with_name("obs_profile.backup.json")
        self.data = dict(PROFILE_DEFAULTS)
        self.last_error = ""
        self.recovery_notice = ""
        self._save_lock = threading.RLock()
        self.exists = self.load()

    def _t(self, key, default, **values):
        text = self._translator(key, default) if callable(self._translator) else default
        try:
            return text.format(**values)
        except (KeyError, ValueError, IndexError):
            return text

    def load(self):
        source = self.path if self.path.exists() else LEGACY_PROFILE_PATH
        if not source.exists():
            return False
        try:
            loaded = json.loads(source.read_text(encoding="utf-8-sig"))
            if not isinstance(loaded, dict):
                raise ValueError("la racine JSON doit être un objet")
            self.data.update(loaded)
            if self._migrate():
                self.save()
            return True
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            if source == self.path and self._recover_from_backup(error):
                return True
            self.last_error = self._t("obs_profile_unreadable", "Profil OBS illisible : {error}", error=error)
            return False

    def _recover_from_backup(self, original_error):
        if not self.backup_path.exists():
            return False
        try:
            loaded = json.loads(self.backup_path.read_text(encoding="utf-8-sig"))
            if not isinstance(loaded, dict):
                return False
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            return False
        if self.path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            try:
                shutil.copy2(self.path, self.path.with_name(f"obs_profile.corrupt-{stamp}.json"))
            except OSError:
                pass
        self.data.update(loaded)
        self._migrate()
        self.recovery_notice = self._t("obs_profile_recovered", "Le profil OBS endommagé a été restauré depuis sa sauvegarde.")
        self.last_error = self._t("obs_profile_recovery_detail", "Restauration du profil OBS après erreur : {error}", error=original_error)
        return self.save(create_backup=False)

    def _migrate(self):
        changed = False
        version = int(self.data.get("version", 1))
        if version < 2:
            old_fallback = str(self.data.get("fallback_scene", "")).strip()
            self.data["fallback_enabled"] = bool(old_fallback)
            self.data.setdefault("fallback_delay_ms", 2000)
            parent = str(self.data.get("stream_scene", "Stream")).strip() or "Stream"
            self.data["parent_scenes"] = [parent]
            changed = True
        if version < PROFILE_VERSION:
            custom_ids = [
                str(item.get("id")) for item in self.data.get("custom_controls", [])
                if isinstance(item, dict) and item.get("id") and item.get("command")
            ]
            self.data["streamdeck_order"] = list(BUILTIN_STREAMDECK_IDS) + custom_ids
            self.data["streamdeck_hidden_controls"] = []
            changed = True
        self.data["version"] = PROFILE_VERSION
        for key, value in PROFILE_DEFAULTS.items():
            if key not in self.data:
                self.data[key] = value
                changed = True
        scene_migrations = {
            "game_scene": {"DOSOFT — Dofus", "Jeu_Dofus"},
            "retro_game_scene": {"Jeu Dofus Retro"},
            "wakfu_game_scene": {"Jeu Dofus Wakfu"},
        }
        for key, legacy_values in scene_migrations.items():
            if str(self.data.get(key, "")).strip() in legacy_values:
                self.data[key] = PROFILE_DEFAULTS[key]
                changed = True
        if self._repair_game_scene_names():
            changed = True
        if normalize_streamdeck_profile(self.data):
            changed = True
        return changed

    def _repair_game_scene_names(self):
        """Keep one distinct managed scene per engine.

        A historical UI bug could save ``Jeu_Wakfu`` into ``game_scene``.
        Inventory detection then checked Wakfu twice and falsely reported that
        all three engines were ready.  Foreign defaults and duplicate custom
        names are repaired deterministically without touching valid choices.
        """
        keys = ("game_scene", "retro_game_scene", "wakfu_game_scene")
        defaults = {key: str(PROFILE_DEFAULTS[key]).strip() for key in keys}
        changed = False
        for key in keys:
            value = str(self.data.get(key, "")).strip()
            foreign_defaults = {
                default.casefold() for other_key, default in defaults.items()
                if other_key != key
            }
            if not value or value.casefold() in foreign_defaults:
                value = defaults[key]
            if self.data.get(key) != value:
                self.data[key] = value
                changed = True

        used = set()
        for key in keys:
            value = str(self.data[key]).strip()
            normalized = value.casefold()
            if normalized in used:
                value = defaults[key]
                normalized = value.casefold()
                if self.data[key] != value:
                    self.data[key] = value
                    changed = True
            used.add(normalized)
        return changed

    def save(self, create_backup=True):
        temporary = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        error = None
        with self._save_lock:
            for attempt in range(3):
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    if create_backup and self.path.exists():
                        try:
                            existing = json.loads(self.path.read_text(encoding="utf-8-sig"))
                            if isinstance(existing, dict):
                                shutil.copy2(self.path, self.backup_path)
                        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
                            pass
                    self.data["version"] = PROFILE_VERSION
                    self._repair_game_scene_names()
                    payload = json.dumps(self.data, ensure_ascii=False, indent=2) + "\n"
                    temporary.write_text(payload, encoding="utf-8")
                    # Refuse to replace a valid profile with incomplete JSON.
                    json.loads(temporary.read_text(encoding="utf-8"))
                    os.replace(temporary, self.path)
                    self.exists = True
                    self.last_error = ""
                    return True
                except PermissionError as caught:
                    error = caught
                    if attempt < 2:
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    break
                except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as caught:
                    error = caught
                    break

            self.last_error = self._t(
                "obs_profile_save_failed",
                "Impossible d’enregistrer le profil OBS : {error}",
                error=error,
            )
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def reset(self):
        try:
            if self.path.exists():
                self.path.unlink()
            self.data = dict(PROFILE_DEFAULTS)
            self.exists = False
            self.last_error = ""
            return True
        except OSError as exc:
            self.last_error = self._t("obs_profile_reset_failed", "Impossible de réinitialiser le profil OBS : {error}", error=exc)
            return False


class DosoftObsBridge:
    """Bidirectional named-pipe bridge. It is inert while the extension is disabled."""

    def __init__(self, config, translator=None):
        self.config = config
        self._translator = translator
        self.profile = ObsProfile(translator=translator)
        self.last_status = self._t("obs_status_disabled", "OBS: extension disabled")
        self.last_inventory = {"scenes": [], "sources": [], "audio_sources": []}
        self._status_lock = threading.Lock()
        self.connection_state = "disabled" if not self.enabled else "connecting"
        self._last_state_message = None
        self.plugin_version = ""
        self.obs_version = ""
        self.compatibility_warnings = []
        self.protocol_version = None
        self.capabilities = frozenset()
        self.plugin_session_id = ""
        self.last_seen = 0.0
        self.consecutive_failures = 0
        self._handshake_in_flight = False
        self._handshake_callbacks = []
        self._revision = int(time.time() * 1000)
        self.debug_log_path = APP_DATA_DIR / "dosoft-obs-debug.log"
        self._outbox = deque()
        self._outbox_condition = threading.Condition()
        self._last_sync_signature = None
        self._last_sync_time = 0.0
        self._worker = threading.Thread(
            target=self._outbox_worker, name="DOSOFT-OBS", daemon=True
        )
        self._worker.start()

    def _t(self, key, default, **values):
        text = self._translator(key, default) if callable(self._translator) else default
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text

    @property
    def enabled(self):
        return bool(self.config.data.get("obs_integration_enabled", False))

    def activate(self):
        self.config.data["obs_integration_enabled"] = True
        if not self.config.save():
            self._set_state("degraded", self.config.last_error, force=True)
            return False
        if not self.profile.exists and not self.profile.save():
            self._set_state("degraded", self.profile.last_error, force=True)
            return False
        self._set_state("connecting", self._t("obs_status_connecting", "OBS: connecting locally…"), force=True)
        self._handshake()
        return True

    def deactivate(self):
        if self.enabled:
            self._send_async({"version": 2, "event": "deactivate"})
        self.config.data["obs_integration_enabled"] = False
        self.config.data["obs_auto_swap_enabled"] = False
        self.config.save()
        self.capabilities = frozenset()
        self.plugin_session_id = ""
        self.obs_version = ""
        self.compatibility_warnings = []
        self._set_state("disabled", self._t("obs_status_disabled", "OBS: extension disabled"), force=True)

    def _set_state(self, state, message, force=False):
        unchanged = state == self.connection_state and message == self._last_state_message
        self.connection_state = state
        self._last_state_message = message
        if unchanged and not force:
            return
        self._record(message, force=force)

    def status_snapshot(self):
        with self._status_lock:
            return {
                "state": self.connection_state,
                "message": self.last_status,
                "plugin_version": self.plugin_version,
                "obs_version": self.obs_version,
                "compatibility_warnings": list(self.compatibility_warnings),
                "protocol_version": self.protocol_version,
                "capabilities": sorted(self.capabilities),
                "session_id": self.plugin_session_id,
                "last_seen": self.last_seen,
                "failures": self.consecutive_failures,
            }

    def _profile_payload(self):
        return self._profile_payload_for_engine(self.active_engine())

    def _profile_payload_for_engine(self, engine):
        keys = (
            "stream_scene", "game_scene", "fallback_enabled", "fallback_scene",
            "fallback_delay_ms", "capture_prefix", "max_captures",
        )
        payload = {key: self.profile.data.get(key, PROFILE_DEFAULTS[key]) for key in keys}
        payload["engine"] = engine
        scene_key = {
            "retro": "retro_game_scene",
            "wakfu": "wakfu_game_scene",
        }.get(engine, "game_scene")
        prefix_key = {
            "retro": "retro_capture_prefix",
            "wakfu": "wakfu_capture_prefix",
        }.get(engine, "capture_prefix")
        payload["game_scene"] = str(
            self.profile.data.get(scene_key, PROFILE_DEFAULTS[scene_key])
        ).strip() or PROFILE_DEFAULTS[scene_key]
        payload["capture_prefix"] = str(
            self.profile.data.get(prefix_key, PROFILE_DEFAULTS[prefix_key])
        ).strip() or PROFILE_DEFAULTS[prefix_key]
        return payload

    def expected_game_scenes(self):
        """Return the three managed scene names configured on this computer."""
        return [
            self._profile_payload_for_engine(engine)["game_scene"]
            for engine in ("unity", "retro", "wakfu")
        ]

    def active_engine(self):
        return {
            "Rétro": "retro",
            "Wakfu": "wakfu",
        }.get(self.config.data.get("game_version", "Unity"), "unity")

    def active_game_scene_key(self):
        return {
            "retro": "retro_game_scene",
            "wakfu": "wakfu_game_scene",
        }.get(self.active_engine(), "game_scene")

    def active_capture_prefix_key(self):
        return {
            "retro": "retro_capture_prefix",
            "wakfu": "wakfu_capture_prefix",
        }.get(self.active_engine(), "capture_prefix")

    def active_game_scene(self):
        key = self.active_game_scene_key()
        return str(self.profile.data.get(key, PROFILE_DEFAULTS[key])).strip() or PROFILE_DEFAULTS[key]

    def active_capture_prefix(self):
        key = self.active_capture_prefix_key()
        return str(self.profile.data.get(key, PROFILE_DEFAULTS[key])).strip() or PROFILE_DEFAULTS[key]

    @staticmethod
    def _client_id(account):
        hwnd = int(account.get("hwnd") or 0)
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0
        return f"{pid:x}-{hwnd:x}"

    def _ready_accounts(self, accounts):
        engine = self.active_engine()
        return [
            {
                "client_id": self._client_id(account),
                "account": account["name"],
                "hwnd": int(account["hwnd"]),
                "engine": engine,
            }
            for account in accounts
            if account.get("name") and account.get("hwnd") and not account.get("is_menu", False)
        ]

    def synchronize_team(self, accounts, callback=None):
        if not self.enabled:
            return
        ready = self._ready_accounts(accounts)
        if not ready:
            self._record("Synchronisation différée : aucun personnage Dofus prêt")
            if callback:
                callback({"ok": False, "error": "no_ready_accounts"})
            return
        payload = {
            "version": 2,
            "event": "sync_team",
            "revision": self._revision + 1,
            "profile": self._profile_payload(),
            "auto_swap": self.config.data.get("obs_auto_swap_enabled", False),
            "accounts": ready,
        }
        signature = self._sync_signature(payload)
        # Automatic discovery may rescan a lone/loading client every 20 s.
        # OBS already has the complete state, so an identical background sync
        # must remain a no-op until an account, engine, scene or OBS session
        # actually changes. A manual action carries a callback and still forces
        # a full synchronization.
        if callback is None and signature == self._last_sync_signature:
            return
        # Idempotent and deliberately sent first: switching Unity/Retro/Wakfu
        # must create or migrate that engine's managed scene before captures.
        self.setup_scenes()
        self._revision += 1
        payload["revision"] = self._revision
        self._record(f"Synchronisation v2 demandée : {len(ready)} client(s), révision {self._revision}")
        self._send_async(payload, callback)

    def rebuild_team(self, accounts, callback=None):
        if not self.enabled:
            return
        ready = self._ready_accounts(accounts)
        if not ready:
            self._record("Reconstruction refusée : aucun personnage Dofus prêt")
            if callback:
                callback({"ok": False, "error": "no_ready_accounts"})
            return
        self.setup_scenes()
        self._revision += 1
        self._send_async({
            "version": 2,
            "event": "rebuild_team",
            "revision": self._revision,
            "profile": self._profile_payload(),
            "auto_swap": self.config.data.get("obs_auto_swap_enabled", False),
            "accounts": ready,
        }, callback)

    def setup_scenes(self, parent_scenes=None, callback=None, quiet_not_ready=False):
        if not self.enabled:
            return
        parents = parent_scenes if parent_scenes is not None else self.profile.data.get("parent_scenes", [])
        payload = {
            "version": 2,
            "event": "setup_scenes",
            "profile": self._profile_payload(),
            "parent_scenes": [{"value": value} for value in parents if value],
        }
        self._send_async(payload, callback, quiet_not_ready=quiet_not_ready)

    def ensure_all_game_scenes(self, missing_scenes=None, callback=None):
        """Create every missing managed game scene, then restore the active profile.

        Requests are deliberately serialized through the existing pipe outbox.
        The last request always reapplies the currently selected game engine so
        opening the assistant cannot silently change the live auto-swap target.
        """
        if not self.enabled:
            if callback:
                callback({"ok": False, "error": "extension_disabled"})
            return
        requested = set(missing_scenes or self.expected_game_scenes())
        definitions = [
            (engine, self._profile_payload_for_engine(engine))
            for engine in ("unity", "retro", "wakfu")
        ]
        pending = [item for item in definitions if item[1]["game_scene"] in requested]
        active_engine = self.active_engine()
        active_item = next(item for item in definitions if item[0] == active_engine)
        if not pending or pending[-1][0] != active_engine:
            pending.append(active_item)
        created = [
            profile["game_scene"] for engine, profile in definitions
            if profile["game_scene"] in requested
        ]

        def send_next(index):
            if index >= len(pending):
                if callback:
                    callback({"ok": True, "data": {"created_scenes": created}})
                return
            _, profile = pending[index]
            payload = {
                "version": 2,
                "event": "setup_scenes",
                "profile": profile,
                "parent_scenes": [],
            }

            def completed(response):
                if not response.get("ok"):
                    if callback:
                        callback({
                            "ok": False,
                            "error": response.get("error"),
                            "data": {"failed_scene": profile["game_scene"]},
                        })
                    return
                send_next(index + 1)

            self._send_async(payload, completed)

        send_next(0)

    def query_inventory(self, callback=None):
        if not self.enabled:
            return
        self._send_async({"version": 2, "event": "get_inventory"}, callback)

    def startup_check(self, accounts):
        if not self.enabled:
            return
        if not self.profile.exists:
            self._set_state("profile_required", self._t("obs_status_profile_required", "OBS: profile missing — setup required"))
            return
        def after_handshake(response):
            if not response.get("ok") or self.connection_state == "incompatible":
                return
            # Push the saved scene names only after both sides agreed on the
            # protocol. This also detects a restarted OBS plugin session.
            self.setup_scenes(quiet_not_ready=True)
            self.query_inventory()
            if self._ready_accounts(accounts):
                self.synchronize_team(accounts)
            else:
                self._send_async({"event": "set_auto_swap", "enabled": False})
                self._record("OBS connecté — changement automatique en attente d'un personnage prêt")

        self._handshake(after_handshake)

    def _handshake(self, callback=None, silent=False):
        if not self.enabled:
            return
        if callback:
            self._handshake_callbacks.append(callback)
        if self._handshake_in_flight:
            return
        self._handshake_in_flight = True
        previous_session_before = self.plugin_session_id
        was_connected_before = self.connection_state == "connected"
        if not silent:
            self._set_state("connecting", self._t("obs_status_checking", "OBS: checking the local plugin…"))

        def completed(response):
            self._handshake_in_flight = False
            if not response.get("ok"):
                callbacks, self._handshake_callbacks = self._handshake_callbacks, []
                for pending_callback in callbacks:
                    try:
                        pending_callback(response)
                    except Exception as error:
                        self._record(f"Erreur du retour de connexion OBS : {error}")
                return
            metadata = negotiate_plugin(response)
            if not metadata.get("compatible"):
                self._set_state(
                    "incompatible",
                    self._t("obs_status_plugin_incompatible", "OBS: incompatible plugin — update Dofus Scene Guard."),
                )
                response = {"ok": False, "error": metadata.get("error", "unsupported_protocol")}
            else:
                previous_session = previous_session_before
                was_connected = was_connected_before
                self.plugin_version = metadata["plugin_version"]
                self.obs_version = metadata["obs_version"]
                self.compatibility_warnings = compatibility_warnings(
                    self.plugin_version, self.obs_version, translator=self._translator
                )
                self.protocol_version = metadata["protocol_version"]
                self.capabilities = metadata["capabilities"]
                self.plugin_session_id = metadata["session_id"]
                session_changed = bool(
                    previous_session and self.plugin_session_id
                    and previous_session != self.plugin_session_id
                )
                response["session_changed"] = session_changed
                response["previous_session"] = previous_session
                response["legacy_plugin"] = metadata["legacy"]
                response["was_connected"] = was_connected
                if session_changed:
                    self._last_sync_signature = None
                    self._record("OBS a redémarré : resynchronisation complète requise.")
                compatibility = self._t("obs_compatibility_v2", " (v2 compatibility)") if metadata["legacy"] else ""
                warning = (
                    self._t("obs_attention_prefix", " Warning: ") + " ".join(self.compatibility_warnings)
                    if self.compatibility_warnings else ""
                )
                if silent and was_connected and not session_changed:
                    self.connection_state = "connected"
                else:
                    self._set_state(
                        "connected",
                        self._t(
                            "obs_status_connected",
                            "OBS {obs_version} connected — plugin {plugin_version}, protocol {protocol_version}{compatibility}.{warning}",
                            obs_version=self.obs_version or "?",
                            plugin_version=self.plugin_version,
                            protocol_version=self.protocol_version,
                            compatibility=compatibility,
                            warning=warning,
                        ),
                    )
            callbacks, self._handshake_callbacks = self._handshake_callbacks, []
            for pending_callback in callbacks:
                try:
                    pending_callback(response)
                except Exception as error:
                    self._record(f"Erreur du retour de connexion OBS : {error}")

        self._send_async({"event": "hello"}, completed)

    def ensure_connection(self, accounts):
        """Lightweight health check and state rebuild after an OBS restart."""
        if not self.enabled or not self.profile.exists or self.connection_state == "incompatible":
            return
        if self._handshake_in_flight:
            return
        if self.connection_state == "connected" and time.time() - self.last_seen < 1.0:
            return

        def recovered(response):
            if not response.get("ok"):
                return
            if not should_resynchronize(
                response.get("previous_session", ""),
                self.plugin_session_id,
                response.get("was_connected", False),
                response.get("legacy_plugin", False),
            ):
                return
            self.setup_scenes(quiet_not_ready=True)
            self.query_inventory()
            if self._ready_accounts(accounts):
                self.synchronize_team(accounts)
            else:
                self._send_async({"event": "set_auto_swap", "enabled": False})
            self._record("OBS reconnecté — configuration DOSOFT resynchronisée.")

        # A background probe must not alternate the visible/logged state between
        # "connecting" and "disconnected" while OBS is closed. The transport
        # failure itself still records the first real disconnection transition.
        self._handshake(recovered, silent=True)

    def selected_account(self, account):
        if not self.enabled or not self.config.data.get("obs_auto_swap_enabled", False):
            return
        self._send_async({
            "version": 2,
            "event": "dofus_account_selected",
            "client_id": self._client_id(account),
            "account": account["name"],
            "hwnd": int(account["hwnd"]),
            "engine": self.active_engine(),
        })

    def set_auto_swap(self, enabled):
        self.config.data["obs_auto_swap_enabled"] = bool(enabled) if self.enabled else False
        self.config.save()
        if self.enabled:
            self._send_async({"version": 2, "event": "set_auto_swap", "enabled": bool(enabled)})

    def control(self, command, callback=None):
        if not self.enabled or not self.profile.exists:
            return
        profile = self.profile.data
        mapping = {
            "toggle_microphone": (profile["microphone_source"], ""),
            "toggle_camera": (profile["camera_source"], profile["camera_scene"]),
            "toggle_pause": ("", profile["pause_scene"]),
        }
        source, scene = mapping[command]
        self.control_custom(command, source, scene, callback)

    def control_custom(self, command, source="", scene="", callback=None):
        if not self.enabled:
            return
        self._send_async({
            "version": 2,
            "event": "obs_control",
            "command": command,
            "source": source,
            "scene": scene,
        }, callback)

    def query_control_state(self, command, source="", scene="", callback=None):
        if not self.enabled:
            return
        self._send_async({
            "version": 2,
            "event": "obs_control_state",
            "command": command,
            "source": source,
            "scene": scene,
        }, callback)

    def _send_async(self, payload, callback=None, quiet_not_ready=False):
        if not self.enabled:
            return
        payload = prepare_request(payload)
        payload.setdefault("request_id", uuid.uuid4().hex)
        event = payload.get("event", "")
        if event != "hello" and (
            self.connection_state != "connected" or self._handshake_in_flight
        ):
            # Never let stale streamdeck polls or scene commands overtake the
            # handshake after OBS starts/restarts. The successful handshake
            # callback rebuilds the complete configuration in the right order.
            response = {"ok": False, "error": "connection_not_ready"}
            if callback:
                callback(response)
            return
        capability = required_capability(event)
        if self.capabilities and capability and capability not in self.capabilities:
            response = {"ok": False, "error": "unsupported_capability", "capability": capability}
            self._set_state(
                "degraded",
                self._t(
                    "obs_status_capability_update",
                    "OBS: feature “{capability}” requires a plugin update.",
                    capability=capability,
                ),
            )
            if callback:
                callback(response)
            return
        coalesce_key = event if event in {
            "get_inventory", "sync_team", "dofus_account_selected", "set_auto_swap"
        } else None
        with self._outbox_condition:
            if coalesce_key:
                for item in reversed(self._outbox):
                    if item["key"] == coalesce_key:
                        item["payload"] = payload
                        if callback:
                            item["callbacks"].append(callback)
                        self._outbox_condition.notify()
                        return
            self._outbox.append({
                "key": coalesce_key,
                "payload": payload,
                "callbacks": [callback] if callback else [],
                "quiet_not_ready": bool(quiet_not_ready),
            })
            self._outbox_condition.notify()

    def _outbox_worker(self):
        """Serialize access to OBS' single-instance named pipe.

        OBS accepts one client at a time. Keeping exactly one request in flight
        prevents startup inventory checks, automatic refreshes and manual syncs
        from racing each other and silently losing the profile update.
        """
        while True:
            with self._outbox_condition:
                while not self._outbox:
                    self._outbox_condition.wait()
                item = self._outbox.popleft()
            payload = item["payload"]
            response = self._send_with_retry(
                payload, quiet_not_ready=item.get("quiet_not_ready", False)
            )
            if payload.get("event") == "sync_team":
                if response.get("ok"):
                    self._last_sync_signature = self._sync_signature(payload)
                    self._last_sync_time = time.monotonic()
                else:
                    self._last_sync_signature = None
            for callback in item["callbacks"]:
                try:
                    callback(response)
                except Exception as error:
                    self._record(f"Erreur du retour interface OBS : {error}")

    def _send_with_retry(self, payload, quiet_not_ready=False):
        """Retry only idempotent commands; never repeat a toggle control."""
        retryable_events = {
            "get_inventory", "setup_scenes", "sync_team",
            "rebuild_team", "set_auto_swap", "deactivate",
        }
        attempts = 3 if payload.get("event") in retryable_events else 1
        response = {"ok": False, "error": "transport_error"}
        for attempt in range(attempts):
            response = self._send(payload, quiet_not_ready=quiet_not_ready)
            if response.get("error") != "transport_error":
                return response
            if attempt + 1 < attempts:
                time.sleep(0.25 * (attempt + 1))
        return response

    @staticmethod
    def _sync_signature(payload):
        stable = {
            "profile": payload.get("profile", {}),
            "auto_swap": payload.get("auto_swap", False),
            "accounts": payload.get("accounts", []),
        }
        return json.dumps(stable, ensure_ascii=False, sort_keys=True)

    def _send(self, payload, quiet_not_ready=False):
        try:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            with open(PIPE_NAME, "r+b", buffering=0) as pipe:
                pipe.write(encoded)
                response_bytes = pipe.read(64 * 1024)
            # An empty read means OBS closed the named pipe while shutting
            # down. It is a transport disconnect, not a protocol mismatch.
            if not response_bytes:
                raise OSError("empty_pipe_response")
            response = json.loads(response_bytes.decode("utf-8"))
            protocol_error = validate_response(response, payload.get("request_id", ""))
            if protocol_error:
                self._set_state(
                    "incompatible" if protocol_error == "unsupported_protocol" else "degraded",
                    self._t("obs_status_invalid_response", "OBS: invalid or incompatible plugin response."),
                )
                return {"ok": False, "error": protocol_error}
            self.consecutive_failures = 0
            self.last_seen = time.time()
            if response.get("ok"):
                data = response.get("data") or {}
                if isinstance(data, dict) and "scenes" in data:
                    self.last_inventory = data
                    if payload.get("event") != "hello":
                        self._set_state(
                            "connected",
                            self._t(
                                "obs_status_inventory",
                                "OBS connected — plugin {plugin_version}, {count} scene(s) detected",
                                plugin_version=data.get("plugin_version", "?"),
                                count=len(data.get("scenes", [])),
                            ),
                        )
                elif payload.get("event") != "hello":
                    if self.connection_state != "incompatible":
                        self.connection_state = "connected"
                    # Polling the three native streamdeck controls is routine
                    # telemetry, not a user-visible command confirmation.
                    if payload.get("event") not in {
                        "obs_control_state", "dofus_account_selected",
                    }:
                        self._record(self._success_message(payload.get("event")))
            else:
                error = response.get("error")
                if error == "unsupported_protocol":
                    self._set_state("incompatible", self._t("obs_status_versions_incompatible", "OBS: incompatible DOSOFT/plugin versions."))
                elif error in {
                    "invalid_envelope", "request_id_mismatch", "invalid_response",
                    "unknown_event", "unsupported_capability",
                }:
                    self._set_state("degraded", self._error_message(payload.get("event"), error))
                else:
                    # OBS answered a valid request, so the local transport is
                    # healthy. A missing scene/source is a configuration error,
                    # not an unstable connection. In particular, native
                    # Streamdeck state polling must remain silent when a user
                    # has not created CAM, Pause or Mic/Aux yet.
                    if self.connection_state != "incompatible":
                        self.connection_state = "connected"
                    if (
                        payload.get("event") != "obs_control_state"
                        and not (quiet_not_ready and error == "operation_not_ready")
                    ):
                        self._record(self._error_message(payload.get("event"), error))
            return response
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.consecutive_failures += 1
            if self.connection_state != "disconnected":
                self._record(
                    "Diagnostic OBS : rupture du transport local "
                    f"event={payload.get('event', '?')} détail={type(error).__name__}:{error}"
                )
            self._set_state(
                "disconnected",
                self._t("obs_status_disconnected", "OBS disconnected — make sure OBS is open."),
            )
            return {"ok": False, "error": "transport_error", "detail": str(error)}

    def _success_message(self, event):
        messages = {
            "setup_scenes": ("obs_success_setup", "Connection successful: the DOSOFT scene is linked to OBS."),
            "sync_team": ("obs_success_sync", "Synchronization successful: detected characters are ready in OBS."),
            "rebuild_team": ("obs_success_rebuild", "Emergency restart successful: DOSOFT captures were recreated."),
            "set_auto_swap": ("obs_success_autoswap", "Automatic character switching was updated."),
            "obs_control": ("obs_success_control", "Streamdeck command executed by OBS."),
            "deactivate": ("obs_success_deactivate", "The OBS extension was stopped."),
        }
        key, default = messages.get(event, ("obs_success_default", "Command confirmed by OBS."))
        return self._t(key, default)

    def _error_message(self, event, error):
        if error == "operation_not_ready":
            if event in {"sync_team", "rebuild_team"}:
                return self._t("obs_error_no_ready_window", "OBS is still waiting for a ready Dofus window. The last capture remains displayed.")
            if event == "setup_scenes":
                return self._t("obs_error_setup_incomplete", "Incomplete connection: check the main scene name in OBS.")
            return self._t("obs_error_command", "OBS could not apply this command. Check the selected scene or source.")
        if error == "unknown_event":
            return self._t("obs_error_unknown_event", "The OBS plugin version is not compatible with this DOSOFT command.")
        if error == "unsupported_capability":
            return self._t("obs_error_unsupported_capability", "This feature requires a newer OBS plugin.")
        if error in {"unsupported_protocol", "invalid_envelope", "request_id_mismatch"}:
            return self._t("obs_error_protocol", "The OBS plugin protocol is incompatible or its response is invalid.")
        return self._t("obs_error_connection", "OBS connection interrupted. Make sure OBS is open and the plugin is loaded.")

    def _record(self, message, force=False):
        if not self.enabled and not force:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        with self._status_lock:
            self.last_status = line
            if not self.profile.data.get("diagnostics_enabled", False):
                return
            try:
                append_rotating(self.debug_log_path, line, max_bytes=1_000_000, backup_count=2)
            except Exception:
                pass
