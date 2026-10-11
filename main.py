import os
import sys
import re

# The beta build uses a portable Tcl/Tk runtime.  When frozen, configure it
# before importing tkinter so the packaged executable is self-contained.
if getattr(sys, "frozen", False):
    _bundle_dir = getattr(sys, "_MEIPASS", "")
    _tcl_dir = os.path.join(_bundle_dir, "tcl8.6")
    _tk_dir = os.path.join(_bundle_dir, "tk8.6")
    if os.path.isdir(_tcl_dir) and os.path.isdir(_tk_dir):
        # Override PyInstaller's default runtime hook: its automatic Tcl/Tk
        # discovery cannot see DOSOFT's portable runtime during the build.
        os.environ["TCL_LIBRARY"] = _tcl_dir
        os.environ["TK_LIBRARY"] = _tk_dir

import ctypes
import threading
import queue
import keyboard
import time
import win32api
import win32con
import win32gui
import win32process
from PIL import Image
import tkinter as tk
import customtkinter as ctk
import pystray
from pystray import MenuItem as item
import asyncio
import requests
import webbrowser
from tkinter import messagebox 
from app_version import CURRENT_VERSION, APP_TITLE

# --- FORCAGE DU DPI AWARENESS (Règle les soucis 4K / Zoom Windows) ---
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except: pass

try:
    from winrt.windows.ui.notifications.management import UserNotificationListener
    from winrt.windows.ui.notifications import NotificationKinds, UserNotificationChangedKind
    WINSDK_AVAILABLE = True
except ImportError:
    WINSDK_AVAILABLE = False

from config_manager import Config, default_settings_path
from dofus_settings_manager import DofusSettingsManager
from dosoft_obs_bridge import APP_DATA_DIR, PROFILE_PATH, DosoftObsBridge
from obs_stream_dock import ObsStreamDock
from logic import DofusLogic
from gui import OrganizerGUI
from radial_menu import RadialMenu
from i18n_manager import I18nManager
from keyboard_layout_manager import KeyboardLayoutManager
from wakfu_log_watcher import WakfuLogWatcher
from retro_debug import begin_retro_debug_session, write_retro_debug
from hotkey_debug import write_hotkey_debug
from retro_notification_engine import RetroNotificationEngine, EVENT_PATTERNS
from resource_paths import skin_path
from character_bar import CharacterQuickBar
from runtime_policy import should_run_retro_autofocus
from hotkey_policy import normalize_hotkey
from release_backup import ensure_release_backup
from compatibility import load_compatibility_manifest


def try_load_windows_layout(layout_name):
    layout_map = {
        "azerty_fr": "0000040C",
        "qwerty_us": "00000409",
    }
    layout_code = layout_map.get(layout_name)
    if not layout_code:
        return
    try:
        ctypes.windll.user32.LoadKeyboardLayoutW(layout_code, 1 | 0x00000100)
    except Exception:
        pass


class OrganizerApp:
    def __init__(self, config=None):
        self.config = config or Config()
        self._shutting_down = False
        self.retro_notification_engine = None
        self.i18n = I18nManager(self.config.data.get("language", "fr"))
        self.keymaps = KeyboardLayoutManager(self.config.data.get("keyboard_layout", "azerty_fr"))
        try_load_windows_layout(self.config.data.get("keyboard_layout", "azerty_fr"))
        self.dofus_settings = DofusSettingsManager(translator=self.i18n.t)
        self.obs_bridge = DosoftObsBridge(self.config, self.i18n.t)
        self.logic = DofusLogic(self.config, self._notify_obs_account_selected)
        # While the settings window records a new shortcut, existing global
        # shortcuts must not execute actions or steal the same key press.
        self.hotkey_capture_active = False
        self.gui = OrganizerGUI(self)
        self._config_error_visible = False
        self.config.error_handler = self._on_config_save_error
        self.character_bar = CharacterQuickBar(
            self.gui.root,
            self.config,
            self.focus_character_from_bar,
            self.set_character_bar_visible,
            self.select_team_from_bar,
        )
        self.character_bar.update_theme(
            self.gui.game_theme, self.config.data.get("game_version", "Unity")
        )
        if self.config.data.get("character_bar_visible", False):
            self.character_bar.set_visible(True)
        self.current_idx = 0
        self.hotkey_actions = {} 
        self.mouse_hotkeys = {}
        self.mouse_states = {}
        self.hotkey_sources = {}
        self.mouse_hotkey_sources = {}
        self._reserved_hotkeys = {}
        self._registered_hotkey_values = {}
        self.radial_hotkey_runtime = ""
        self._hotkey_conflicts = []
        self._last_hotkey_conflict_signature = None
        self.pending_auto_focus = None
        self.auto_focus_defer_scheduled = False
        self._autofocus_requests = queue.Queue()
        self._retro_debug_states = {}
        self._retro_last_wait_trace = 0.0
        self.pending_cycle_direction = None
        self.cycle_defer_scheduled = False
        # Global keyboard/mouse hooks run outside Tk's message thread. Window
        # focus must never be performed from those callback threads: Windows
        # can temporarily mark the target GUI as busy and display the spinning
        # cursor. Queue each physical press once for the Tk event loop instead.
        self._hotkey_requests = queue.Queue(maxsize=64)
        self._pressed_hotkey_scans = set()
        self._focused_account_refresh_requested = threading.Event()
        self._focused_account_refresh_hwnd = 0
        
        self.radial_focus = RadialMenu(
            self.gui.root,
            self.on_radial_focus_select,
            accent_color="#2ecc71",
            hover_color="#27ae60",
            center_icon_path=skin_path("character"),
        )
        
        saved_vol = self.config.data.get("volume_level", 50) / 100.0
        self.radial_focus.set_base_volume(saved_vol)
        
        threading.Thread(target=self.background_listener, daemon=True).start()
        
        self.setup_hotkeys()
        self.refresh()

        # An enabled extension reconnects on every DOSOFT launch. A missing
        # explicit profile is reported instead of silently using hard-coded
        # OBS names.
        self.gui.root.after(800, lambda: self.obs_bridge.startup_check(self.logic.all_accounts))
        self.gui.root.after(900, self.refresh_obs_stream_dock)
        self.gui.root.after(5000, self.auto_refresh_watchdog)
        self.gui.root.after(2500, self.obs_connection_watchdog)
        self.refresh_retro_notification_listener()
        self.gui.root.after(50, self._poll_auto_focus_requests)
        self.gui.root.after(10, self._poll_hotkey_requests)
        self.gui.root.after(100, self._poll_focused_account_refresh)
        self.start_wakfu_log_listener()
        self.setup_system_tray()
        
        self.gui.root.after(1000, self.check_conflicting_software)
        self.gui.root.after(1200, self.start_version_check)
        if self.config.recovery_notice:
            self.gui.root.after(350, self._show_config_recovery_notice)

    def _on_config_save_error(self, message):
        """Surface persistence failures on Tk's thread instead of hiding them."""
        if self._shutting_down:
            return

        def show_error():
            if self._config_error_visible or self._shutting_down:
                return
            self._config_error_visible = True
            try:
                self.gui.show_temporary_message(self.i18n.t("settings_save_failed", "Paramètres non enregistrés."), "#e05b5b")
                messagebox.showerror(self.i18n.t("settings_error_title", "Paramètres DoSoft"), message, parent=self.gui.root)
            finally:
                self._config_error_visible = False

        try:
            self.gui.root.after(0, show_error)
        except tk.TclError:
            pass

    def start_version_check(self):
        """Check for updates away from Tk; being offline is never an error."""
        def worker():
            update = check_version(self.i18n)
            if update is None or self._shutting_down:
                return
            current, latest = update

            def notify():
                if self._shutting_down:
                    return
                open_download = messagebox.askyesno(
                    self.i18n.t("version_update_required_title", "Mise à jour disponible"),
                    self.i18n.t(
                        "version_update_required_text",
                        "Une nouvelle version de DoSoft est disponible.\n\n"
                        "Votre version : {current_version}\n"
                        "Version disponible : {latest_version}\n\n"
                        "Téléchargez puis exécutez le nouveau setup par-dessus l’installation actuelle. "
                        "Vos réglages seront sauvegardés et conservés.\n\n"
                        "Ouvrir la page de téléchargement ?",
                    ).format(current_version=current, latest_version=latest),
                    parent=self.gui.root,
                )
                if open_download:
                    webbrowser.open(
                        load_compatibility_manifest().get(
                            "manual_update_url", "https://dosoft.fr"
                        )
                    )

            try:
                self.gui.root.after(0, notify)
            except tk.TclError:
                pass

        threading.Thread(target=worker, name="DOSOFT-VersionCheck", daemon=True).start()

    def reset_to_defaults(self):
        """Reset persistent files and immediately rebuild every live service."""
        self.obs_bridge.deactivate()
        profile_ok = self.obs_bridge.profile.reset()
        config_ok = self.config.reset_settings()
        if not profile_ok or not config_ok:
            return False, self.config.last_error or self.obs_bridge.profile.last_error

        defaults = self.config.data
        self.i18n.set_locale(defaults["language"])
        self.keymaps.set_layout(defaults["keyboard_layout"])
        try_load_windows_layout(defaults["keyboard_layout"])
        self.current_idx = 0
        self.pending_cycle_direction = None
        self.pending_auto_focus = None
        self.logic.all_accounts = []
        self.logic.leader_hwnd = None
        self.refresh_retro_notification_listener()
        self.setup_hotkeys()

        bar = getattr(self, "character_bar", None)
        if bar is not None:
            bar.update_accounts([], defaults["game_version"])
            bar.set_visible(False)
        dock = getattr(self, "obs_stream_dock", None)
        if dock is not None:
            dock.withdraw()
        return True, ""

    def _show_config_recovery_notice(self):
        messagebox.showinfo(
            self.i18n.t("settings_error_title", "Paramètres DoSoft"),
            self.config.recovery_notice,
            parent=self.gui.root,
        )

    def setup_system_tray(self):
        icon_path = "logo.ico" 
        try: image = Image.open(icon_path)
        except: image = Image.new('RGB', (64, 64), color=(44, 62, 80))

        menu = pystray.Menu(
            item(self.i18n.t("tray_toggle", "Afficher/Cacher"), self.toggle_from_tray, default=True),
            item(self.i18n.t("tray_sort", "Trier Barre Windows"), self.sort_taskbar_from_tray),
            item(self.i18n.t("tray_refresh", "Rafraîchir"), self.refresh_from_tray),
            item(self.i18n.t("tray_quit", "Quitter"), self.quit_from_tray)
        )
        self.tray_icon = pystray.Icon("dosoft_tray", image, "DOSOFT", menu)
        self.tray_icon.run_detached()

    def _notify_obs_account_selected(self, hwnd):
        """Publish immediately; refresh only if this client's title changed."""
        if not self.obs_bridge.enabled:
            return
        for account in self.logic.all_accounts:
            if account.get("hwnd") == hwnd:
                self.obs_bridge.selected_account(account)
                break
        if self.logic.focused_account_identity_changed(hwnd):
            self._focused_account_refresh_hwnd = hwnd
            self._focused_account_refresh_requested.set()

    def _poll_focused_account_refresh(self):
        """Run the rare rename rebuild on Tk, never inside the hotkey callback."""
        if self._shutting_down:
            return
        if self._focused_account_refresh_requested.is_set():
            self._focused_account_refresh_requested.clear()
            hwnd = self._focused_account_refresh_hwnd
            self._focused_account_refresh_hwnd = 0
            self.refresh()
            # ``refresh`` queues the complete OBS team first. Queue the new
            # identity behind it so a login/character rename selects the newly
            # created source rather than the stale one.
            for account in self.logic.all_accounts:
                if account.get("hwnd") == hwnd:
                    self.obs_bridge.selected_account(account)
                    break
        self.gui.root.after(100, self._poll_focused_account_refresh)

    def refresh_obs_stream_dock(self):
        """Create, show or hide the optional dock immediately after profile edits."""
        should_show = (self.config.data.get("obs_integration_enabled", False)
                       and self.obs_bridge.profile.exists
                       and self.obs_bridge.profile.data.get("dock_enabled", False))
        dock = getattr(self, "obs_stream_dock", None)
        if should_show and dock is None:
            self.obs_stream_dock = ObsStreamDock(self.gui.root, self.obs_bridge)
            self.gui.root.after(80, self.obs_stream_dock.show_and_recover)
            self.obs_bridge._record("DOCK : créé et affiché")
        elif should_show:
            try:
                exists = bool(dock.winfo_exists())
            except Exception:
                exists = False
            if not exists:
                self.obs_stream_dock = ObsStreamDock(self.gui.root, self.obs_bridge)
                dock = self.obs_stream_dock
            dock.rebuild_buttons()
            # rebuild_buttons performs one atomic fit/show after Tk has measured
            # the new controls. Showing here would expose the old native frame
            # for a few milliseconds before the final geometry is applied.
            self.obs_bridge._record("DOCK : reconstruction demandée")
        elif dock is not None:
            dock.withdraw()
            self.obs_bridge._record("DOCK : masqué")

    def sync_obs_team(self, callback=None):
        """Create/update OBS scenes for the currently detected Dofus team."""
        slots = self.logic.scan_slots()
        self.gui.refresh_list(slots, self.config.data.get("game_version", "Unity"))
        self.obs_bridge.synchronize_team(slots, callback)

    def rebuild_obs_team(self, callback=None):
        """Remove only Dofus Scene Guard sources then recreate the current team."""
        slots = self.logic.scan_slots()
        self.gui.refresh_list(slots, self.config.data.get("game_version", "Unity"))
        self.obs_bridge.rebuild_team(slots, callback)

    def toggle_from_tray(self, icon, item):
        def safe_toggle():
            if self.gui.root.state() == 'withdrawn':
                self.gui.root.deiconify()
                self.gui.root.lift()
                self.gui.root.focus_force()
            else:
                self.gui.root.withdraw()
        self.gui.root.after(0, safe_toggle)

    def refresh_from_tray(self, icon, item):
        self.gui.root.after(0, self.refresh)

    def sort_taskbar_from_tray(self, icon, item):
        self.gui.root.after(0, self.gui.trigger_sort_taskbar)

    def quit_from_tray(self, icon, item):
        self.gui.root.after(0, self.shutdown)

    def update_volume(self, volume_val):
        self.config.data["volume_level"] = volume_val
        self.config.save()
        vol_float = volume_val / 100.0
        self.radial_focus.set_base_volume(vol_float)

    def check_conflicting_software(self):
        if self.config.data.get("ignore_organizer_warning", False):
            return
        try:
            output = os.popen('tasklist /FI "IMAGENAME eq organizer.exe" /NH').read().lower()
            if "organizer.exe" in output:
                self.show_conflict_popup()
        except Exception: pass

    def show_conflict_popup(self):
        popup = ctk.CTkToplevel(self.gui.root)
        popup.title(self.i18n.t("popup_conflict_title", "⚠️ Conflit de logiciels détecté"))
        popup.geometry("480x250")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.transient(self.gui.root)
        
        popup.update_idletasks()
        x = self.gui.root.winfo_x() + (self.gui.root.winfo_width() // 2) - (480 // 2)
        y = self.gui.root.winfo_y() + (self.gui.root.winfo_height() // 2) - (250 // 2)
        popup.geometry(f"+{x}+{y}")

        msg = self.i18n.t(
            "popup_conflict_text",
            "Le logiciel 'Organizer' est actuellement ouvert.\nL'utilisation de deux gestionnaires de pages simultanément\nva créer des bugs et des conflits de focus sur DOSOFT.\n\nNous vous recommandons fortement de le fermer."
        )
        
        lbl = ctk.CTkLabel(popup, text=msg, justify="center", font=ctk.CTkFont(size=13))
        lbl.pack(pady=(20, 15))

        var_ignore = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(popup, text=self.i18n.t("popup_conflict_ignore", "Ne plus m'afficher cet avertissement"), variable=var_ignore)
        chk.pack(pady=(0, 20))

        frame_btn = ctk.CTkFrame(popup, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20)

        def on_close_organizer():
            if var_ignore.get():
                self.config.data["ignore_organizer_warning"] = True
                self.config.save()
            os.system("taskkill /F /IM organizer.exe /T")
            popup.destroy()
            self.gui.show_temporary_message(self.i18n.t("msg_organizer_closed", "✅ Organizer fermé avec succès !"), "#2ecc71")

        def on_keep_organizer():
            if var_ignore.get():
                self.config.data["ignore_organizer_warning"] = True
                self.config.save()
            popup.destroy()

        btn_close = ctk.CTkButton(frame_btn, text=self.i18n.t("btn_close_organizer", "Fermer Organizer"), fg_color="#27ae60", hover_color="#2ecc71", command=on_close_organizer)
        btn_close.pack(side="left", expand=True, padx=10)

        btn_keep = ctk.CTkButton(frame_btn, text=self.i18n.t("btn_keep_running", "Conserver"), fg_color="#7f8c8d", hover_color="#95a5a6", command=on_keep_organizer)
        btn_keep.pack(side="right", expand=True, padx=10)
        
        popup.grab_set()

    def get_vk(self, key_str):
        key_str = key_str.lower().strip()
        mapping = {
            "alt": win32con.VK_MENU, "ctrl": win32con.VK_CONTROL, "shift": win32con.VK_SHIFT,
            "left_click": 0x01, "right_click": 0x02, "middle_click": 0x04,
            "mouse4": 0x05, "mouse5": 0x06
        }
        if key_str in mapping: return mapping[key_str]
        
        scan_code = self.keymaps.key_to_scan(key_str)
        if scan_code is not None:
            vk = ctypes.windll.user32.MapVirtualKeyW(scan_code, 1) 
            if vk: return vk
            
        if len(key_str) == 1:
            vk_scan = ctypes.windll.user32.VkKeyScanW(ord(key_str))
            vk = vk_scan & 0xFF
            if vk != 0xFF:
                return vk
            return ord(key_str.upper())
        if key_str.startswith('f') and key_str[1:].isdigit():
            return 0x6F + int(key_str[1:])
        return None

    def is_hotkey_pressed(self, hk_str):
        if not hk_str: return False
        parts = hk_str.split('+')
        for p in parts:
            token = p.lower().strip()
            if token in {"ctrl", "alt", "shift"}:
                vk = self.get_vk(token)
                if vk is None or win32api.GetAsyncKeyState(vk) >= 0:
                    return False
                continue

            mouse_vk = self.get_vk(token) if "click" in token or "mouse" in token else None
            if mouse_vk is not None:
                if win32api.GetAsyncKeyState(mouse_vk) >= 0:
                    return False
                continue

            scan_code = self.keymaps.resolve_scan_code(token)
            if scan_code is not None:
                if not keyboard.is_pressed(scan_code):
                    return False
            elif not keyboard.is_pressed(token):
                return False
        return True

    def background_listener(self):
        radial_was_open = False
        
        while not self._shutting_down:
            if self.hotkey_capture_active:
                # Forget pressed mouse states so releasing the button used to
                # select a shortcut cannot trigger an existing action.
                self.mouse_states = {}
                radial_was_open = False
                time.sleep(0.02)
                continue

            # Gestion des macros de souris (MB4, MB5, Clics)
            if hasattr(self, 'mouse_hotkeys'):
                # setup_hotkeys may replace the mapping from the Tk thread.
                # Iterate over a snapshot so the listener cannot die with
                # "dictionary changed size during iteration".
                for hk_str, func in list(self.mouse_hotkeys.items()):
                    is_pressed = self.is_hotkey_pressed(hk_str)
                    was_pressed = self.mouse_states.get(hk_str, False)
                    
                    if is_pressed and not was_pressed:
                        self.mouse_states[hk_str] = True
                        self._queue_hotkey_action(func)
                    elif not is_pressed and was_pressed:
                        self.mouse_states[hk_str] = False

            # Gestion de la roue radiale
            radial_hk = self.radial_hotkey_runtime
            radial_active = self.config.data.get("radial_menu_active", True)
            
            if radial_active and radial_hk:
                is_pressed = self.is_hotkey_pressed(radial_hk)
                
                if is_pressed and not radial_was_open:
                    radial_was_open = True
                    game_version = self.config.data.get("game_version", "Unity")
                    class_engine = "retro" if game_version == "Rétro" else "wakfu" if game_version == "Wakfu" else "unity"

                    # Chaque moteur fournit son propre visuel de classe.
                    active_accs = []
                    for acc in self.logic.get_cycle_list():
                        cls = acc.get('classe', 'Inconnu')
                        active_accs.append({'name': acc['name'], 'classe': cls, 'hwnd': acc['hwnd']})
                    
                    fg_hwnd = win32gui.GetForegroundWindow()
                    current_name = None
                    for acc in active_accs:
                        if acc['hwnd'] == fg_hwnd:
                            current_name = acc['name']
                            break
                            
                    x, y = win32api.GetCursorPos()
                    self.gui.root.after(
                        0, self.radial_focus.show, x, y, active_accs, current_name, class_engine
                    )
                    
                elif radial_was_open and not is_pressed:
                    radial_was_open = False
                    self.gui.root.after(0, self.radial_focus.hide)

            # Synchronisation de l'index au clic manuel
            try:
                fg_hwnd = win32gui.GetForegroundWindow()
                cycle_list = self.logic.get_cycle_list()
                if cycle_list:
                    for index, acc in enumerate(cycle_list):
                        if acc['hwnd'] == fg_hwnd:
                            if self.current_idx != index:
                                self.current_idx = index
                            break
            except Exception: pass
            time.sleep(0.01)

    def on_radial_focus_select(self, target_name):
        for acc in self.logic.all_accounts:
            if acc['name'] == target_name:
                self.logic.focus_window(acc['hwnd'])
                break
        
        cycle_list = self.logic.get_cycle_list()
        for index, acc in enumerate(cycle_list):
            if acc['name'] == target_name:
                self.current_idx = index
                break

    def register_action(self, hk_str, func, source="Action"):
        if not hk_str: return
        hk_str = normalize_hotkey(hk_str)
        if hk_str in self._reserved_hotkeys:
            self._hotkey_conflicts.append(
                (hk_str, self._reserved_hotkeys[hk_str], source)
            )
            write_hotkey_debug(
                f"CONFLICT hotkey={hk_str!r} kept={self._reserved_hotkeys[hk_str]!r} ignored={source!r}",
                "warning",
            )
            return False
        
        if 'click' in hk_str or 'mouse' in hk_str:
            if hk_str in self.mouse_hotkeys:
                self._hotkey_conflicts.append(
                    (hk_str, self.mouse_hotkey_sources.get(hk_str, "Action"), source)
                )
                write_hotkey_debug(
                    f"CONFLICT hotkey={hk_str!r} kept={self.mouse_hotkey_sources.get(hk_str)!r} ignored={source!r}",
                    "warning",
                )
                return False
            self.mouse_hotkeys[hk_str] = func
            self.mouse_hotkey_sources[hk_str] = source
            self._registered_hotkey_values[hk_str] = source
            return True
            
        parts = hk_str.split('+')
        mods = set()
        main_scan = None
        for p in parts:
            if p in ['ctrl', 'alt', 'shift']:
                mods.add(p)
                continue
            main_scan = self.keymaps.resolve_scan_code(p)
        if main_scan is not None:
            action_key = (frozenset(mods), main_scan)
            if action_key in self.hotkey_actions:
                self._hotkey_conflicts.append(
                    (hk_str, self.hotkey_sources.get(action_key, "Action"), source)
                )
                write_hotkey_debug(
                    f"CONFLICT hotkey={hk_str!r} kept={self.hotkey_sources.get(action_key)!r} ignored={source!r}",
                    "warning",
                )
                return False
            self.hotkey_actions[action_key] = func
            self.hotkey_sources[action_key] = source
            self._registered_hotkey_values[hk_str] = source
            return True
        return False

    def _report_hotkey_conflicts(self):
        signature = tuple(sorted(set(self._hotkey_conflicts)))
        if not signature:
            self._last_hotkey_conflict_signature = None
            return
        if signature == self._last_hotkey_conflict_signature:
            return
        self._last_hotkey_conflict_signature = signature
        details = "\n".join(
            self.i18n.t(
                "hotkey_conflict_detail",
                "• {hotkey} : {kept} est conservé, {ignored} est ignoré.",
            ).format(hotkey=hotkey.upper(), kept=kept, ignored=ignored)
            for hotkey, kept, ignored in signature
        )

        def notify():
            messagebox.showwarning(
                self.i18n.t("hotkey_conflict_title", "Conflit de raccourcis"),
                self.i18n.t(
                    "hotkey_conflict_runtime_message",
                    "Plusieurs actions utilisent la même touche. DOSOFT a conservé la première action pour éviter un comportement imprévisible.\n\n{details}",
                ).format(details=details),
                parent=self.gui.root,
            )

        try:
            self.gui.root.after(0, notify)
        except tk.TclError:
            pass

    def _execute_advanced_and_update(self, mode, identifier):
        new_idx = self.logic.execute_advanced_bind(mode, identifier)
        if new_idx != -1: 
            self.current_idx = new_idx

    def release_modifiers(self):
        """Force Windows à relâcher les touches Ctrl, Alt et Shift après la saisie."""
        try:
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
        except: pass

    def restore_modifiers(self, mods):
        """Compatibility no-op: never synthesize a modifier key-down.

        Restoring a physical modifier with keybd_event could leave Alt, Ctrl or
        Shift logically pressed after the user had already released it.
        """
        return

    def global_hook_listener(self, event):
        if self.hotkey_capture_active:
            self._pressed_hotkey_scans.clear()
            return
        if event.event_type == keyboard.KEY_UP:
            if self.config.data.get("hotkey_chord_overlap_enabled", False):
                # Experimental stacked-chord mode: releasing only the main
                # key rearms it while Alt/Ctrl/Shift may stay physically held.
                self._pressed_hotkey_scans.discard(event.scan_code)
            else:
                # Safe mode requires the complete chord to be released. This
                # prevents a held modifier from unexpectedly repeating actions
                # after a focus change or delayed Windows key event.
                modifier_still_down = any(
                    win32api.GetAsyncKeyState(vk) < 0
                    for vk in (win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_SHIFT)
                )
                if not modifier_still_down:
                    self._pressed_hotkey_scans.clear()
            return
        if event.event_type != keyboard.KEY_DOWN:
            return
        
        current_mods = set()
        if win32api.GetAsyncKeyState(win32con.VK_CONTROL) < 0: current_mods.add('ctrl')
        if win32api.GetAsyncKeyState(win32con.VK_MENU) < 0: current_mods.add('alt')
        if win32api.GetAsyncKeyState(win32con.VK_SHIFT) < 0: current_mods.add('shift')
        
        key = (frozenset(current_mods), event.scan_code)
        if key in self.hotkey_actions:
            if event.scan_code in self._pressed_hotkey_scans:
                return
            self._pressed_hotkey_scans.add(event.scan_code)
            self._queue_hotkey_action(self.hotkey_actions[key])

    def _queue_hotkey_action(self, action):
        """Transfer a hook action to Tk without creating a worker per press."""
        try:
            self._hotkey_requests.put_nowait(action)
        except queue.Full:
            write_hotkey_debug("ACTION_DROPPED reason=queue_full", "warning")

    def _poll_hotkey_requests(self):
        """Execute serialized shortcuts on the GUI thread and keep focus fluid."""
        if self._shutting_down:
            return
        processed = 0
        while processed < 8:
            try:
                action = self._hotkey_requests.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception as exc:
                write_hotkey_debug(f"ACTION_ERROR error={exc!r}", "exception")
            processed += 1
        try:
            self.gui.root.after(10, self._poll_hotkey_requests)
        except tk.TclError:
            pass

    def setup_hotkeys(self):
        if self.hotkey_capture_active:
            write_hotkey_debug("SETUP_SKIPPED reason=capture_active")
            return
        keyboard.unhook_all()
        self.hotkey_actions = {} 
        self.mouse_hotkeys = {} 
        self.mouse_states = {}  
        self._pressed_hotkey_scans.clear()
        self.hotkey_sources = {}
        self.mouse_hotkey_sources = {}
        self._reserved_hotkeys = {}
        self._registered_hotkey_values = {}
        self.radial_hotkey_runtime = ""
        self._hotkey_conflicts = []
        
        cfg = self.config.data

        try:
            # Essential controls always win over advanced binds. Existing
            # conflicting profiles remain usable and receive a clear warning.
            if cfg.get("prev_key"): self.register_action(cfg["prev_key"], self.prev_char, "Personnage précédent")
            if cfg.get("next_key"): self.register_action(cfg["next_key"], self.next_char, "Personnage suivant")
            if cfg.get("leader_key"): self.register_action(cfg["leader_key"], self.focus_leader, "Chef")
            if cfg.get("toggle_app_key"): self.register_action(cfg["toggle_app_key"], lambda: self.gui.root.after(0, self.gui.toggle_visibility), "Afficher/cacher DOSOFT")
            if cfg.get('refresh_key'): self.register_action(cfg['refresh_key'], self.refresh, "Actualiser")
            if cfg.get('quit_key'): self.register_action(cfg['quit_key'], self.quit_app, "Quitter DOSOFT")
            if not cfg.get("fast_switch_team_disabled", False) and cfg.get("team_switch_key"):
                self.register_action(cfg["team_switch_key"], self.switch_team_mode, "Changer d’équipe")
            if cfg.get("radial_menu_active", True) and cfg.get("radial_menu_hotkey"):
                radial = normalize_hotkey(cfg["radial_menu_hotkey"])
                if radial in self._registered_hotkey_values:
                    self._hotkey_conflicts.append(
                        (radial, self._registered_hotkey_values[radial], "Roue radiale")
                    )
                else:
                    # The radial action is polled separately. Reserve its
                    # shortcut without synthesizing or releasing any key.
                    self.radial_hotkey_runtime = radial
                    self._reserved_hotkeys[radial] = "Roue radiale"

            mode = cfg.get("advanced_bind_mode", "cycle")
            if mode == "cycle":
                for index, bind_str in enumerate(cfg.get("cycle_row_binds", [])):
                    if bind_str:
                        self.register_action(
                            bind_str,
                            lambda idx=index: self._execute_advanced_and_update("cycle", idx),
                            f"Ligne {index + 1}",
                        )
            elif mode == "bind":
                for pseudo, bind_str in cfg.get("persistent_character_binds", {}).items():
                    if bind_str:
                        self.register_action(
                            bind_str,
                            lambda ps=pseudo: self._execute_advanced_and_update("bind", ps),
                            f"Personnage {pseudo}",
                        )
            keyboard.hook(self.global_hook_listener)
            self._report_hotkey_conflicts()
        except Exception as exc:
            write_hotkey_debug(f"SETUP_ERROR error={exc!r}", "exception")

    def refresh(self):
        # The scan result is valid only for the engine selected at its start.
        # A queued Tk callback from a previous engine must never repaint the
        # current UI with stale WAKFU/Rétro/Unity accounts.
        source_version = self.config.data.get("game_version", "Unity")
        slots = self.logic.scan_slots()
        if self.obs_bridge.enabled:
            self.obs_bridge.synchronize_team(slots)
        self.gui.root.after(0, self.gui.refresh_list, slots, source_version)

    def auto_refresh_watchdog(self):
        """Refresh newly launched games without forcing users to press F5.

        A detected login/menu is intentionally checked less often than a
        single-character launch, avoiding needless scans while the player is
        choosing a character.
        """
        try:
            target_running = self.logic.has_target_game_window()
            accounts = list(self.logic.all_accounts)
            has_waiting_menu = any(account.get("is_menu", False) for account in accounts)
            characters_detected = sum(not account.get("is_menu", False) for account in accounts)

            if target_running and has_waiting_menu:
                self.refresh()
                delay_ms = 60_000
            elif target_running and characters_detected < 2:
                self.refresh()
                delay_ms = 20_000
            else:
                # No game (or a healthy group): inexpensive process/window
                # detection continues so a later launch is picked up.
                delay_ms = 5_000
        except Exception:
            delay_ms = 5_000
        self.gui.root.after(delay_ms, self.auto_refresh_watchdog)

    def obs_connection_watchdog(self):
        """Reconnect and restore the OBS contract after an OBS restart."""
        if not self._shutting_down:
            try:
                self.obs_bridge.ensure_connection(list(self.logic.all_accounts))
            except Exception as exc:
                self.obs_bridge._record(f"Contrôle de connexion OBS impossible : {exc}")
            self.gui.root.after(2000, self.obs_connection_watchdog)

    def change_game_engine(self, version):
        """Atomically discard the previous engine's cycle before rescanning."""
        self.config.data["game_version"] = version
        self.config.save()
        self.current_idx = 0
        self.pending_cycle_direction = None
        self.pending_auto_focus = None
        self.logic.all_accounts = []
        self.logic.leader_hwnd = None
        bar = getattr(self, "character_bar", None)
        if bar:
            bar.update_accounts([], version)
        self.refresh_retro_notification_listener()

    def set_character_bar_visible(self, visible):
        self.config.data["character_bar_visible"] = bool(visible)
        self.config.save()
        bar = getattr(self, "character_bar", None)
        if bar:
            bar.set_visible(bool(visible))
        gui = getattr(self, "gui", None)
        if gui and hasattr(gui, "var_character_bar"):
            gui.var_character_bar.set(bool(visible))

    def focus_character_from_bar(self, account):
        """Focus a clicked quick-bar character and preserve cycle order."""
        self.logic.focus_window(account.get("hwnd"))
        cycle_list = self.logic.get_cycle_list()
        for index, candidate in enumerate(cycle_list):
            if candidate.get("hwnd") == account.get("hwnd"):
                self.current_idx = index
                break

    def select_team_from_bar(self, team):
        """Use the quick-bar ghost tab to switch to the other active team."""
        if self.config.data.get("fast_switch_team_disabled", False):
            return
        self.set_team_mode(team)

    def switch_team_mode(self):
        """Toggle Team 1/Team 2 from the optional global bind.

        ALL remains available in the normal selector, but it is not a team and
        therefore no longer interrupts a rapid two-team workflow.
        """
        current = self.config.data.get("current_mode", "ALL")
        target = "Team 2" if current == "Team 1" else "Team 1"
        self.gui.root.after(0, self.set_team_mode, target)

    def set_team_mode(self, team):
        """Change the active team without rebuilding DoSoft's account list."""
        if team not in ("ALL", "Team 1", "Team 2"):
            return False
        self.logic.set_mode(team)
        cycle_list = self.logic.get_cycle_list()
        try:
            foreground = win32gui.GetForegroundWindow()
        except Exception:
            foreground = 0
        self.current_idx = next(
            (index for index, account in enumerate(cycle_list) if account.get("hwnd") == foreground),
            0,
        )
        self.gui.combo_mode.set(team)
        bar = getattr(self, "character_bar", None)
        if bar:
            bar.update_accounts(
                self.logic.all_accounts,
                self.config.data.get("game_version", "Unity"),
                immediate=True,
            )
        return True

    def set_team_mode_from_shortcut(self, team):
        """Compatibility entry point retained for older callbacks/tests."""
        return self.set_team_mode(team)

    def start_wakfu_log_listener(self):
        log_path = os.path.join(
            os.environ.get("APPDATA", ""), "zaap", "gamesLogs", "wakfu", "logs", "wakfu.log"
        )
        self.wakfu_log_watcher = WakfuLogWatcher(
            log_path,
            None,
            self.on_wakfu_fighter_identified,
        )
        self.wakfu_log_watcher.start()

    def on_wakfu_fighter_identified(self, fighter_id, pseudo):
        """Store the game fighter ID seen in the log for its WAKFU character."""
        fighter_ids = self.config.data.setdefault("wakfu_fighter_ids", {})
        if fighter_ids.get(str(fighter_id)) != pseudo:
            fighter_ids[str(fighter_id)] = pseudo
            self.config.save()
            print(f"[WAKFU] Fighter ID {fighter_id} associé à {pseudo}.")

    @staticmethod
    def _mouse_button_is_down():
        return any(
            win32api.GetAsyncKeyState(button) < 0
            for button in (0x01, 0x02, 0x04, 0x05, 0x06)
        )

    def focus_leader(self):
        if self.logic.leader_hwnd: 
            self.logic.focus_window(self.logic.leader_hwnd)
            cycle_list = self.logic.get_cycle_list()
            leader_name = self.config.data.get("leader_name", "")
            for index, acc in enumerate(cycle_list):
                if acc['name'] == leader_name:
                    self.current_idx = index
                    break

    def next_char(self):
        self._request_cycle_step(1)

    def prev_char(self):
        self._request_cycle_step(-1)

    def _request_cycle_step(self, direction):
        """Defer TAB/² page changes until all physical mouse buttons are up."""
        if self._mouse_button_is_down():
            self.pending_cycle_direction = direction
            if not self.cycle_defer_scheduled:
                self.cycle_defer_scheduled = True
                self.gui.root.after(30, self._apply_pending_cycle_step)
            return
        self._apply_cycle_step(direction)

    def _apply_pending_cycle_step(self):
        if self._mouse_button_is_down():
            self.gui.root.after(30, self._apply_pending_cycle_step)
            return
        direction = self.pending_cycle_direction
        self.pending_cycle_direction = None
        self.cycle_defer_scheduled = False
        if direction is not None:
            self._apply_cycle_step(direction)

    def _apply_cycle_step(self, direction):
        cycle_list = self.logic.get_cycle_list()
        if not cycle_list:
            return
        # Resolve the index from the actual foreground window.  The previous
        # cached index may belong to the other team after a Fast Switch and
        # could otherwise skip a character or jump unpredictably.
        try:
            foreground = win32gui.GetForegroundWindow()
        except Exception:
            foreground = 0
        active_index = next(
            (index for index, account in enumerate(cycle_list) if account.get("hwnd") == foreground),
            None,
        )
        if active_index is None:
            self.current_idx = 0 if direction > 0 else len(cycle_list) - 1
        else:
            self.current_idx = (active_index + direction) % len(cycle_list)
        self.logic.focus_window(cycle_list[self.current_idx]['hwnd'])

    def quit_app(self):
        try:
            self.gui.root.after(0, self.shutdown)
        except tk.TclError:
            pass

    def shutdown(self):
        """Stop global hooks and optional workers before destroying Tk."""
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        engine = self.retro_notification_engine
        self.retro_notification_engine = None
        if engine is not None:
            engine.stop()
        tray = getattr(self, "tray_icon", None)
        if tray is not None:
            try:
                tray.stop()
            except Exception:
                pass
        try:
            self.gui.root.destroy()
        except tk.TclError:
            pass

    def set_retro_autofocus_enabled(self, enabled):
        self.config.data["auto_focus_retro"] = bool(enabled)
        self.config.save()
        self.refresh_retro_notification_listener()

    def refresh_retro_notification_listener(self):
        should_run = should_run_retro_autofocus(self.config.data)
        if should_run and self.retro_notification_engine is None:
            self.start_notification_listener()
        elif not should_run and self.retro_notification_engine is not None:
            self.retro_notification_engine.stop()
            self.retro_notification_engine = None
            self.pending_auto_focus = None

    def start_notification_listener(self):
        if not should_run_retro_autofocus(self.config.data):
            return
        begin_retro_debug_session()
        self._write_retro_diagnostic_snapshot("Démarrage de DOSOFT")
        saved_mode = str(self.config.data.get("notif_api_mode", "Automatique"))
        polling_only = saved_mode.casefold() in {"polling", "polling uniquement"}
        # Migrate the former experimental v1-v4 selector to the single robust
        # hybrid engine. Existing users get the recommended mode automatically.
        normalized_mode = "Polling" if polling_only else "Automatique"
        if saved_mode != normalized_mode:
            self.config.data["notif_api_mode"] = normalized_mode
            self.config.save()
        enabled_events = self.config.data.get("retro_autofocus_events", list(EVENT_PATTERNS))
        self.retro_notification_engine = RetroNotificationEngine(
            self._on_retro_notification_detected,
            write_retro_debug,
            enabled_events=enabled_events,
            polling_only=polling_only,
            remove_after_read=self.config.data.get("retro_remove_notifications", True),
        )
        write_retro_debug(
            f"[ETAPE 2] Moteur Auto-Focus unifié : {normalized_mode}. "
            f"Événements actifs : {', '.join(enabled_events) or 'aucun'}."
        )
        self.retro_notification_engine.start()

    def update_retro_autofocus_events(self, enabled_events):
        """Persist and apply Retro notification filters without a restart."""
        requested = set(enabled_events or [])
        ordered = [event for event in EVENT_PATTERNS if event in requested]
        self.config.data["retro_autofocus_events"] = ordered
        self.config.save()
        engine = getattr(self, "retro_notification_engine", None)
        if engine is not None:
            engine.set_enabled_events(ordered)
        write_retro_debug(
            "[FILTRES] Événements Auto-Focus actifs : "
            + (", ".join(ordered) if ordered else "aucun")
        )

    def _on_retro_notification_detected(self, pseudo, event_type, source, body, notification_id):
        """Receive a parsed toast from the worker without touching Tk directly."""
        self.request_auto_focus(
            "Rétro", pseudo=pseudo, reason=event_type, source=source,
            details={"body": body, "notification_id": notification_id},
        )

    def request_auto_focus(self, game, pseudo=None, hwnd=None, reason="", source="", details=None):
        """Thread-safe entry point shared by every game detector."""
        self._autofocus_requests.put({
            "game": game, "pseudo": pseudo, "hwnd": hwnd, "reason": reason,
            "source": source, "details": details or {}, "requested_at": time.monotonic(),
        })

    def _poll_auto_focus_requests(self):
        """Resolve detection events on Tk's thread; the newest valid request wins."""
        latest = None
        try:
            while True:
                latest = self._autofocus_requests.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            self._prepare_auto_focus_request(latest)
        try:
            self.gui.root.after(50, self._poll_auto_focus_requests)
        except tk.TclError:
            pass

    def _autofocus_enabled_for(self, game):
        return game == "Rétro" and bool(
            self.config.data.get("auto_focus_retro", False)
        )

    def _prepare_auto_focus_request(self, request):
        game = request["game"]
        if self.config.data.get("game_version") != game or not self._autofocus_enabled_for(game):
            self._log_auto_focus(request, "IGNORÉ", "moteur ou option désactivé")
            return

        # A character switch keeps the same HWND on Retro. Refresh immediately
        # so a notification for the new character cannot resolve against stale
        # account names.
        if game == "Rétro" and request.get("pseudo"):
            slots = self.logic.scan_slots()
            self.gui.refresh_list(slots, game)

        target = None
        target_index = None
        wanted_name = str(request.get("pseudo") or "").strip().casefold()
        for index, account in enumerate(self.logic.get_cycle_list()):
            same_hwnd = request.get("hwnd") and account.get("hwnd") == request["hwnd"]
            same_name = wanted_name and str(account.get("name", "")).strip().casefold() == wanted_name
            if same_hwnd or same_name:
                target, target_index = account, index
                break
        if target is None:
            self._log_auto_focus(request, "IGNORÉ", "personnage absent de la boucle active")
            return
        if not win32gui.IsWindow(target.get("hwnd")):
            self._log_auto_focus(request, "IGNORÉ", "fenêtre fermée ou recréée")
            return

        request["target"] = target
        request["target_index"] = target_index
        self.pending_auto_focus = request
        if not self.auto_focus_defer_scheduled:
            self.auto_focus_defer_scheduled = True
            self.gui.root.after(0, self._apply_pending_auto_focus)

    def _apply_pending_auto_focus(self):
        """Focus only after all physical mouse buttons have been released."""
        request = self.pending_auto_focus
        if request is None:
            self.auto_focus_defer_scheduled = False
            return
        game = request["game"]
        if self.config.data.get("game_version") != game or not self._autofocus_enabled_for(game):
            self.pending_auto_focus = None
            self.auto_focus_defer_scheduled = False
            self._log_auto_focus(request, "ANNULÉ", "moteur ou option modifié")
            return
        if self._mouse_button_is_down():
            self.gui.root.after(30, self._apply_pending_auto_focus)
            return

        self.pending_auto_focus = None
        self.auto_focus_defer_scheduled = False
        target = request["target"]
        hwnd = target["hwnd"]
        if not win32gui.IsWindow(hwnd):
            self._log_auto_focus(request, "ANNULÉ", "fenêtre devenue invalide")
            return
        focused = self.logic.focus_window(hwnd)
        if focused:
            self.current_idx = request["target_index"]
        self._log_auto_focus(
            request, "TENTATIVE", f"résultat={focused} détail={self.logic.last_focus_debug}"
        )
        self.gui.root.after(250, self._verify_auto_focus, request, hwnd)

    def _verify_auto_focus(self, request, hwnd):
        actual = win32gui.GetForegroundWindow()
        if actual == hwnd:
            self._log_auto_focus(request, "SUCCÈS", "premier plan confirmé")
        else:
            self._log_auto_focus(
                request, "REFUSÉ",
                f"cible={hex(hwnd)} premier_plan={hex(actual) if actual else 'aucun'}",
            )

    @staticmethod
    def _log_auto_focus(request, state, detail):
        target = request.get("target") or {}
        message = (
            f"AUTOFOCUS {state} jeu={request.get('game')} source={request.get('source')} "
            f"raison={request.get('reason')} personnage="
            f"{target.get('name') or request.get('pseudo')!r} {detail}"
        )
        write_retro_debug(message)

    def _retro_trace_state(self, key, value):
        """Write state transitions once, without flooding the diagnostic log."""
        if self._retro_debug_states.get(key) != value:
            self._retro_debug_states[key] = value
            write_retro_debug(f"STATE {key}={value}")

    def _write_retro_diagnostic_snapshot(self, stage):
        """Record the exact prerequisites that matter to the Retro autofocus."""
        game_version = self.config.data.get("game_version", "Unity")
        autofocus = bool(self.config.data.get("auto_focus_retro", False))
        notification_engine = self.config.data.get("notif_api_mode", "v2")
        try:
            cycle = self.logic.get_cycle_list()
            detected = self.logic.all_accounts
            active_names = ", ".join(str(account.get("name", "?")) for account in cycle) or "aucun"
        except Exception as exc:
            write_retro_debug(
                f"[ETAPE - ECHEC] Impossible de lire les comptes détectés : {type(exc).__name__}:{exc!s:.180}"
            )
            return
        write_retro_debug(
            f"[ETAPE 1 - ETAT] {stage} | moteur_jeu={game_version} | autofocus_retro={'ON' if autofocus else 'OFF'} "
            f"| moteur_notifications={notification_engine} | comptes_detectes={len(detected)} "
            f"| comptes_actifs={len(cycle)} [{active_names}]"
        )

    @staticmethod
    def _retro_notification_texts(notification):
        """Extract visible notification text without assuming a fixed binding shape."""
        visual = notification.notification.visual
        bindings = list(visual.bindings)
        texts = []
        for binding in bindings:
            texts.extend(str(item.text or "").strip() for item in binding.get_text_elements())
        return [text for text in texts if text]

    @staticmethod
    def _retro_pseudo_from_texts(texts):
        """Accept the normal title and minor casing/spacing variants from Windows."""
        for text in texts:
            match = re.match(r"^\s*(?P<pseudo>.+?)\s*-\s*dofus\s+r[ée]tro\s*$", text, re.IGNORECASE)
            if match:
                pseudo = match.group("pseudo").strip()
                return pseudo or None
        return None

    def _handle_retro_notification(self, notification, engine_name, baseline=False):
        """Validate one new toast and schedule a safe focus attempt when eligible."""
        notification_id = getattr(notification, "id", "unknown")
        try:
            texts = self._retro_notification_texts(notification)
        except Exception as exc:
            write_retro_debug(
                f"NOTIFICATION_READ_FAILED engine={engine_name} id={notification_id} "
                f"error={type(exc).__name__}:{exc!s:.180}"
            )
            return False

        pseudo = self._retro_pseudo_from_texts(texts)
        preview = " | ".join(texts)[:240]
        if not pseudo:
            write_retro_debug(
                f"[NOTIFICATION] Reçue mais ignorée : elle ne correspond pas à Dofus Rétro "
                f"(moteur={engine_name}, id={notification_id}, texte={preview!r})."
            )
            return False

        game_version = self.config.data.get("game_version", "Unity")
        autofocus_enabled = bool(self.config.data.get("auto_focus_retro", False))
        self._retro_trace_state("game_version", game_version)
        self._retro_trace_state("auto_focus_retro", autofocus_enabled)

        if baseline:
            write_retro_debug(
                f"[NOTIFICATION] Notification Rétro déjà présente au démarrage, volontairement ignorée "
                f"(moteur={engine_name}, id={notification_id}, pseudo={pseudo!r})."
            )
            return True
        if game_version != "Rétro":
            write_retro_debug(
                f"[NOTIFICATION] Reçue pour {pseudo!r}, pas de swap : le moteur sélectionné est {game_version!r}, "
                "pas 'Rétro'."
            )
            return True
        if not autofocus_enabled:
            write_retro_debug(
                f"[NOTIFICATION] Reçue pour {pseudo!r}, pas de swap : Auto-Focus Rétro est désactivé."
            )
            return True

        cycle_list = self.logic.get_cycle_list()
        if not cycle_list:
            write_retro_debug(
                f"[NOTIFICATION] Reçue pour {pseudo!r}, pas de swap : aucun compte actif dans la boucle DOSOFT."
            )
            return True

        normalized_pseudo = pseudo.casefold()
        for index, account in enumerate(cycle_list):
            if str(account.get("name", "")).strip().casefold() != normalized_pseudo:
                continue
            hwnd = account.get("hwnd")
            if not hwnd or not win32gui.IsWindow(hwnd):
                write_retro_debug(
                    f"[SWAP - ECHEC] {pseudo!r} est trouvé dans la boucle mais sa fenêtre n'est plus valide "
                    f"(index={index}, hwnd={hwnd!r})."
                )
                return True
            write_retro_debug(
                f"[SWAP - DEMANDE] Notification reçue pour {pseudo!r} : bascule vers la page {index + 1} "
                f"(moteur={engine_name}, hwnd={hex(hwnd)})."
            )
            self.gui.root.after(0, self._focus_retro_notification_target, hwnd, index, pseudo, engine_name)
            return True

        known_names = ", ".join(str(acc.get("name", "")) for acc in cycle_list)[:240]
        write_retro_debug(
            f"[SWAP - ECHEC] Notification reçue pour {pseudo!r}, mais ce personnage n'est pas dans la boucle active "
            f"(comptes actifs : {known_names!r})."
        )
        return True

    def _focus_retro_notification_target(self, hwnd, index, pseudo, engine_name):
        """Run the actual focus on Tk's thread and verify the Windows result."""
        if self.config.data.get("game_version") != "Rétro" or not self.config.data.get("auto_focus_retro", False):
            write_retro_debug(
                f"[SWAP - ANNULE] {pseudo!r} : le moteur ou l'option Auto-Focus a changé avant la bascule."
            )
            return
        if not hwnd or not win32gui.IsWindow(hwnd):
            write_retro_debug(
                f"[SWAP - ANNULE] {pseudo!r} : la fenêtre ciblée a été fermée avant la bascule."
            )
            return

        foreground_before = win32gui.GetForegroundWindow()
        try:
            focused = self.logic.focus_window(hwnd)
        except Exception as exc:
            write_retro_debug(
                f"[SWAP - ECHEC] {pseudo!r} : erreur Windows {type(exc).__name__}:{exc!s:.180}"
            )
            return

        if focused:
            self.current_idx = index
        write_retro_debug(
            f"[SWAP - TENTATIVE] {pseudo!r} : demande Windows envoyée={focused}, "
            f"détail={getattr(self.logic, 'last_focus_debug', 'unknown')!r}, "
            f"fenêtre_avant={hex(foreground_before) if foreground_before else 'aucune'}."
        )
        self.gui.root.after(250, self._verify_retro_notification_focus, hwnd, pseudo, engine_name)

    def _verify_retro_notification_focus(self, hwnd, pseudo, engine_name):
        foreground = win32gui.GetForegroundWindow()
        if foreground == hwnd:
            write_retro_debug(
                f"[SWAP - SUCCES] {pseudo!r} est bien passé au premier plan."
            )
        else:
            write_retro_debug(
                f"[SWAP - REFUSE] Windows n'a pas donné le premier plan à {pseudo!r} "
                f"(cible={hex(hwnd)}, premier_plan_reel={hex(foreground) if foreground else 'aucun'})."
            )

    async def _poll_retro_notifications(self, engine_name, poll_delay, remove_after_read=False):
        """Shared, guarded notification reader used by the three legacy engines."""
        while True:
            try:
                listener = UserNotificationListener.current
                access = await listener.request_access_async()
                access_value = getattr(access, "value", access)
                self._retro_trace_state("notification_access", str(access_value))
                if access != 1:
                    write_retro_debug(
                        f"[ETAPE 3 - ECHEC] Permission des notifications Windows refusée (moteur={engine_name}, "
                        f"code={access_value!s}). Autorise DOSOFT dans les paramètres de notifications Windows."
                    )
                    await asyncio.sleep(5)
                    continue

                write_retro_debug(
                    f"[ETAPE 3 - OK] Écoute des notifications Windows active (moteur={engine_name}). "
                    "En attente d'une notification de tour Dofus Rétro..."
                )
                seen_ids = set()
                first_pass = True

                while True:
                    try:
                        notifications = await listener.get_notifications_async(NotificationKinds.TOAST)
                        if first_pass:
                            write_retro_debug(
                                f"[ETAPE 4] {len(notifications)} notification(s) déjà présente(s) : elles ne déclenchent pas de swap."
                            )
                        current_ids = set()
                        for notification in notifications:
                            notification_id = notification.id
                            current_ids.add(notification_id)
                            if notification_id in seen_ids:
                                continue
                            seen_ids.add(notification_id)
                            is_retro = self._handle_retro_notification(
                                notification, engine_name, baseline=first_pass
                            )
                            if remove_after_read and is_retro and not first_pass:
                                try:
                                    await asyncio.sleep(1.0)
                                    listener.remove_notification(notification_id)
                                    write_retro_debug(
                                        f"NOTIFICATION_REMOVED engine={engine_name} id={notification_id}"
                                    )
                                except Exception as exc:
                                    write_retro_debug(
                                        f"NOTIFICATION_REMOVE_FAILED engine={engine_name} id={notification_id} "
                                        f"error={type(exc).__name__}:{exc!s:.180}"
                                    )

                        seen_ids.intersection_update(current_ids)
                        first_pass = False
                        if not current_ids and time.monotonic() - self._retro_last_wait_trace >= 30:
                            self._retro_last_wait_trace = time.monotonic()
                            write_retro_debug(
                                f"[ETAPE 4 - ATTENTE] Aucune nouvelle notification Rétro reçue depuis 30 secondes "
                                f"(moteur={engine_name})."
                            )
                    except Exception as exc:
                        write_retro_debug(
                            f"POLL_FAILED engine={engine_name} error={type(exc).__name__}:{exc!s:.180}"
                        )
                    await asyncio.sleep(poll_delay)
            except Exception as exc:
                write_retro_debug(
                    f"LISTENER_FAILED engine={engine_name} error={type(exc).__name__}:{exc!s:.180}"
                )
            await asyncio.sleep(3)

    async def poll_notifications(self):
        await self._poll_retro_notifications("v1", 0.5)

    # ==========================================
    # MOTEUR V2 : AVEC NETTOYAGE NOTIFICATIONS
    # ==========================================
    async def _poll_notifications_v2(self):
        await self._poll_retro_notifications("v2", 0.5, remove_after_read=True)

    # ==========================================
    # MOTEUR V3 : POLLING RAPIDE SANS NETTOYAGE
    # ==========================================
    async def _poll_notifications_v3(self):
        await self._poll_retro_notifications("v3", 0.3)

    async def _poll_notifications_v4(self):
        """Experimental event-driven Retro autofocus with a slow polling fallback.

        The three legacy engines poll Windows notifications. V4 receives the
        native NotificationChanged event immediately, then performs a light
        ten-second rescan only to recover from a lost event callback.
        """
        while True:
            token = None
            try:
                listener = UserNotificationListener.current
                access = await listener.request_access_async()
                access_value = getattr(access, "value", access)
                self._retro_trace_state("notification_access", str(access_value))
                if access != 1:
                    write_retro_debug(
                        f"[V4 - ECHEC] Permission des notifications Windows refusée (code={access_value!s})."
                    )
                    await asyncio.sleep(5)
                    continue

                baseline_notifications = await listener.get_notifications_async(NotificationKinds.TOAST)
                seen_ids = {notification.id for notification in baseline_notifications}
                write_retro_debug(
                    f"[V4 - OK] Écoute événementielle Windows active. {len(seen_ids)} notification(s) déjà "
                    "présente(s) sont ignorées ; le polling de secours est réglé à 10 secondes."
                )

                def on_notification_changed(_sender, args):
                    """Native callback; never let an event error stop the listener."""
                    try:
                        notification_id = int(args.user_notification_id)
                        change_kind = args.change_kind
                        if change_kind != UserNotificationChangedKind.ADDED:
                            write_retro_debug(
                                f"[V4 - EVENEMENT] Notification {notification_id} ignorée : état={change_kind.name}."
                            )
                            return
                        if notification_id in seen_ids:
                            return
                        seen_ids.add(notification_id)
                        notification = listener.get_notification(notification_id)
                        write_retro_debug(
                            f"[V4 - EVENEMENT] Nouvelle notification Windows reçue (id={notification_id})."
                        )
                        self._handle_retro_notification(notification, "v4-evenement")
                    except Exception as exc:
                        write_retro_debug(
                            f"[V4 - EVENEMENT ECHEC] {type(exc).__name__}:{exc!s:.180}"
                        )

                # Keep the Python callback alive for the full subscription.
                self._retro_notification_event_handler = on_notification_changed
                try:
                    write_retro_debug("[V4 - ETAPE] Abonnement à l'événement Windows NotificationChanged...")
                    token = listener.add_notification_changed(on_notification_changed)
                except OSError as exc:
                    # Some Windows builds grant notification access but reject
                    # the event subscription for desktop processes. Keep v4
                    # usable by dropping to a deliberately slow, stable poll.
                    write_retro_debug(
                        f"[V4 - EVENEMENT INDISPONIBLE] Windows refuse l'abonnement NotificationChanged "
                        f"({type(exc).__name__}:{exc!s:.180}). Bascule automatique vers le polling de secours."
                    )
                    self._retro_notification_event_handler = None
                    await self._poll_retro_notifications("v4-secours", 1.0)
                    return

                write_retro_debug("[V4 - OK] Abonnement événementiel confirmé.")

                while True:
                    await asyncio.sleep(10)
                    try:
                        notifications = await listener.get_notifications_async(NotificationKinds.TOAST)
                        current_ids = {notification.id for notification in notifications}
                        recovered = 0
                        for notification in notifications:
                            if notification.id in seen_ids:
                                continue
                            seen_ids.add(notification.id)
                            recovered += 1
                            self._handle_retro_notification(notification, "v4-secours")
                        seen_ids.intersection_update(current_ids)
                        if recovered:
                            write_retro_debug(
                                f"[V4 - SECOURS] {recovered} notification(s) manquée(s) par l'événement, récupérée(s) par le balayage."
                            )
                        else:
                            write_retro_debug("[V4 - ETAT] Événements actifs ; aucun rattrapage nécessaire.")
                    except Exception as exc:
                        write_retro_debug(
                            f"[V4 - SECOURS ECHEC] {type(exc).__name__}:{exc!s:.180}"
                        )
            except Exception as exc:
                write_retro_debug(
                    f"[V4 - LISTENER ECHEC] {type(exc).__name__}:{exc!s:.180}"
                )
            finally:
                if token is not None:
                    try:
                        listener.remove_notification_changed(token)
                    except Exception:
                        pass
                self._retro_notification_event_handler = None
            await asyncio.sleep(3)
                

VERSION_URL = "https://raw.githubusercontent.com/LuframeCode/Dosoft/main/version.json"


def is_newer_version(candidate, current):
    """Return whether a dotted numeric candidate version is newer than current."""
    def parse(value):
        parts = str(value).split(".")
        if not parts or any(not part.isdigit() for part in parts):
            return None
        return tuple(int(part) for part in parts)

    candidate_parts = parse(candidate)
    current_parts = parse(current)
    if candidate_parts is None or current_parts is None:
        return False
    length = max(len(candidate_parts), len(current_parts))
    candidate_parts += (0,) * (length - len(candidate_parts))
    current_parts += (0,) * (length - len(current_parts))
    return candidate_parts > current_parts


def check_version(i18n=None):
    """Return ``(current, latest)`` when an update exists, otherwise None."""
    try:
        response = requests.get(VERSION_URL, timeout=5)
        response.raise_for_status() 
        data = response.json()
        latest_version = data.get("version")

        if latest_version and is_newer_version(latest_version, CURRENT_VERSION):
            return CURRENT_VERSION, latest_version
    except Exception:
        # DoSoft is fully local-first. No connection must never block startup
        # or create an alarming dialog for the user.
        return None
    return None
        

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def run_as_admin():
    if getattr(sys, 'frozen', False):
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv[1:]), None, 1)
    else:
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)

def handle_multiple_instances(i18n):
    mutex_name = "DOSOFT_SINGLE_INSTANCE_MUTEX"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        hwnd = win32gui.FindWindow(None, APP_TITLE)
        if hwnd:
            try:
                # ShowWindow waits for the target UI thread.  If an older
                # DOSOFT instance is temporarily busy, that synchronous call
                # can freeze the new launcher indefinitely.  The async form
                # posts the restore request and lets this launcher exit.
                win32gui.ShowWindowAsync(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            root.destroy()
            ctypes.windll.kernel32.CloseHandle(mutex)
            sys.exit(0)
        messagebox.showinfo(
            i18n.t("header_instance_off", "Instance détectée"),
            i18n.t(
                "popup_instance_already_running",
                "DoSoft est déjà en cours de démarrage. Patientez quelques secondes.",
            ),
            parent=root,
        )
        root.destroy()
        ctypes.windll.kernel32.CloseHandle(mutex)
        sys.exit(0)
    return mutex

def start_application():
    if not is_admin():
        run_as_admin()
        sys.exit() 
    ensure_release_backup(
        CURRENT_VERSION,
        APP_DATA_DIR,
        (default_settings_path(), PROFILE_PATH),
    )
    cfg = Config()
    i18n = I18nManager(cfg.data.get("language", "fr"))
    _app_mutex = handle_multiple_instances(i18n)

    app = OrganizerApp(cfg)
    app.gui.run()

if __name__ == "__main__":
    start_application()
