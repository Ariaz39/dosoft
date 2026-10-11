import json
import os
from pathlib import Path
import shutil
import threading
import time
from datetime import datetime


def default_settings_path():
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "DOSOFT" / "settings.json"


class Config:
    def __init__(self, filename=None, legacy_paths=None):
        configured = filename or os.environ.get("DOSOFT_SETTINGS_FILE")
        self.filename = str(Path(configured) if configured else default_settings_path())
        self.path = Path(self.filename)
        self.backup_path = self.path.with_name("settings.backup.json")
        self.last_error = ""
        self.recovery_notice = ""
        # OBS callbacks, the quick bar and Tk can request persistence from
        # different threads.  They must never share the same temporary file.
        self._save_lock = threading.RLock()
        # Installed by OrganizerApp once Tk exists. Keeping persistence free
        # from GUI imports also makes it testable and safe during bootstrap.
        self.error_handler = None
        selected_legacy_paths = self._default_legacy_paths() if legacy_paths is None else legacy_paths
        self.legacy_paths = [Path(value) for value in selected_legacy_paths]
        self.data = self._defaults()
        self.load()

    @staticmethod
    def _defaults():
        return {
            "prev_key": "tab",
            "next_key": "²",
            "hotkey_chord_overlap_enabled": False,
            "leader_key": "mouse5",
            "toggle_app_key": "f12",
            "refresh_key": "f5",
            "quit_key": "",
            "leader_name": "",
            "accounts_state": {},
            "accounts_team": {},
            "current_mode": "ALL",
            "classes": {},
            "custom_order": [],
            "show_tooltips": True,
            "character_bar_visible": False,
            "character_bar_position": [],
            "character_bar_vertical": False,
            "character_bar_compact": False,
            "fast_switch_team_disabled": False,
            "team_switch_key": "",
            "volume_level": 50,
            "tutorial_done": False,
            "radial_menu_active": True,
            "radial_menu_hotkey": "alt+left_click",
            "game_version": "Unity",
            "ignore_organizer_warning": False,
            "auto_focus_retro": False,
            "wakfu_theme": "1",
            "unity_theme": "1",
            "retro_theme": "1",
            "wakfu_fighter_ids": {},
            "advanced_bind_mode": "cycle",
            "advanced_bind_modifier": "ctrl",
            "persistent_character_binds": {},
            "cycle_row_binds": [
                "ctrl+F1", "ctrl+F2", "ctrl+F3", "ctrl+F4",
                "ctrl+F5", "ctrl+F6", "ctrl+F7", "ctrl+F8",
            ],
            "keyboard_layout": "azerty_fr",
            "language": "fr",
            "notif_api_mode": "Automatique",
            "retro_autofocus_events": [
                "combat", "private_message", "trade", "group",
                "challenge", "craft", "pvp",
            ],
            "retro_remove_notifications": True,
            "obs_integration_enabled": False,
            "obs_auto_swap_enabled": False,
            "obs_full_cam_scene": "FULL_CAM",
        }

    def _default_legacy_paths(self):
        # 1.3.7 stored the profile beside the executable/current working folder.
        candidates = [Path.cwd() / "settings.json", Path(__file__).resolve().with_name("settings.json")]
        return [candidate for index, candidate in enumerate(candidates) if candidate not in candidates[:index]]

    @staticmethod
    def _read_mapping(path):
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("la racine JSON doit être un objet")
        return value

    def _migrate_legacy_file(self):
        if self.path.exists():
            return
        for legacy in self.legacy_paths:
            try:
                if legacy.resolve() == self.path.resolve() or not legacy.exists():
                    continue
                loaded = self._read_mapping(legacy)
                self.data.update(loaded)
                if self.save(create_backup=False):
                    self.recovery_notice = (
                        "Les paramètres DoSoft 1.3.7 ont été déplacés vers votre profil Windows."
                    )
                return
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                self.last_error = f"Migration impossible depuis {legacy}: {error}"

    def load(self):
        self._migrate_legacy_file()
        if not self.path.exists():
            self.save(create_backup=False)
            return
        try:
            loaded = self._read_mapping(self.path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            recovered = self._recover_from_backup(error)
            if not recovered:
                self.last_error = f"Paramètres illisibles : {error}"
                self.recovery_notice = (
                    "Le fichier de paramètres est endommagé. DoSoft utilise des réglages sûrs par défaut."
                )
                self._preserve_corrupt_file()
                self.save(create_backup=False)
            return

        self.data.update(loaded)
        if self._migrate_values(loaded):
            self.save()

    def _recover_from_backup(self, original_error):
        if not self.backup_path.exists():
            return False
        try:
            loaded = self._read_mapping(self.backup_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return False
        self._preserve_corrupt_file()
        self.data.update(loaded)
        self.recovery_notice = (
            "Le fichier de paramètres était endommagé. La dernière sauvegarde valide a été restaurée."
        )
        self.last_error = f"Restauration après erreur : {original_error}"
        self.save(create_backup=False)
        return True

    def _preserve_corrupt_file(self):
        if not self.path.exists():
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"settings.corrupt-{stamp}.json")
        try:
            shutil.copy2(self.path, target)
        except OSError:
            pass

    def _migrate_values(self, loaded):
        changed = False
        if (not loaded.get("shortcut_repair_1_3_6")
                and not any(loaded.get(key) for key in ("prev_key", "next_key", "leader_key"))):
            self.data.update({
                "prev_key": "tab",
                "next_key": "²",
                "leader_key": "mouse5",
                "shortcut_repair_1_3_6": True,
            })
            changed = True
        # Up to 1.3.7 the default F12 shortcut terminated DOSOFT. F12 is now
        # the safe "hide/show UI" shortcut; quitting remains available from
        # the tray menu. Only migrate the exact former default combination so
        # deliberately customized shortcuts are never overwritten.
        if (not loaded.get("hide_ui_f12_1_3_8")
                and str(loaded.get("quit_key", "")).casefold() == "f12"
                and str(loaded.get("toggle_app_key", "")).casefold() in {"", "f10"}):
            self.data["toggle_app_key"] = "f12"
            self.data["quit_key"] = ""
            self.data["hide_ui_f12_1_3_8"] = True
            changed = True
        obsolete = (
            "auto_focus_wakfu",
            "wakfu_autofocus_hotkey",
            "wakfu_autofocus_overlay_position",
            "wakfu_autofocus_overlay_screen_position",
        )
        for key in obsolete:
            if key in self.data:
                self.data.pop(key, None)
                changed = True
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
                            self._read_mapping(self.path)
                            shutil.copy2(self.path, self.backup_path)
                        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                            pass
                    payload = json.dumps(self.data, ensure_ascii=False, indent=4) + "\n"
                    temporary.write_text(payload, encoding="utf-8")
                    self._read_mapping(temporary)
                    os.replace(temporary, self.path)
                    self.last_error = ""
                    return True
                except PermissionError as caught:
                    error = caught
                    if attempt < 2:
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    break
                except (OSError, UnicodeError, TypeError, ValueError) as caught:
                    error = caught
                    break

            self.last_error = f"Impossible d’enregistrer les paramètres : {error}"
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            handler = self.error_handler
            if callable(handler):
                try:
                    handler(self.last_error)
                except Exception:
                    pass
            return False

    def reset_settings(self):
        self.data = self._defaults()
        self.recovery_notice = ""
        self.last_error = ""
        return self.save()
