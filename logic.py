import win32gui
import win32con
import win32api
import ctypes
import win32process
import time
import os
import re

from retro_window_layout import maximize_windows, tile_windows


WAKFU_JAVA_PROCESS_NAMES = {"java.exe", "javaw.exe"}
WAKFU_JAVA_WINDOW_CLASSES = ("SunAwt",)
WAKFU_CHARACTER_TITLE = re.compile(r"^\s*(?P<pseudo>.+?)\s*-\s*wakfu\s*$", re.IGNORECASE)
RETRO_CHARACTER_TITLE = re.compile(
    r"^\s*(?P<pseudo>.+?)\s*-\s*dofus\s+r(?:e|é)tro\b", re.IGNORECASE
)
RETRO_LOADING_TITLE = re.compile(r"^\s*dofus\s+r(?:e|é)tro\b", re.IGNORECASE)


def get_window_process_name(hwnd):
    """Return the executable name that owns a window, or an empty string."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
        process_handle = win32api.OpenProcess(access, False, pid)
        try:
            return os.path.basename(win32process.GetModuleFileNameEx(process_handle, 0)).lower()
        finally:
            win32api.CloseHandle(process_handle)
    except Exception:
        return ""


def is_wakfu_window(hwnd, title, class_name, process_name=None):
    """Identify a WAKFU game window without matching unrelated WAKFU titles."""
    if "wakfu" not in title.lower():
        return False

    process_name = process_name if process_name is not None else get_window_process_name(hwnd)
    if process_name.lower() in WAKFU_JAVA_PROCESS_NAMES:
        return True
    return class_name.startswith(WAKFU_JAVA_WINDOW_CLASSES)


def get_wakfu_character_name(title):
    """Extract the character name from the expected `PSEUDO - WAKFU` title."""
    match = WAKFU_CHARACTER_TITLE.match(title)
    return match.group("pseudo").strip() if match else None

class DofusLogic:
    def __init__(self, config, on_window_focused=None):
        self.config = config
        self.on_window_focused = on_window_focused
        self.all_accounts = []
        self.leader_hwnd = None
        self.last_focus_debug = "not_attempted"
        # Login/menu windows do not have a character name yet. EnumWindows can
        # return them in a different order on every refresh, so a scan-local
        # counter makes the loop jump between clients. Keep one tag per live
        # HWND for the whole DOSOFT session instead.
        self._unity_menu_tags = {}
        self._next_unity_menu_tag = 1

    def _prune_unity_menu_tags(self, live_hwnds):
        live_hwnds = set(live_hwnds)
        self._unity_menu_tags = {
            hwnd: tag for hwnd, tag in self._unity_menu_tags.items() if hwnd in live_hwnds
        }
        if not self._unity_menu_tags:
            self._next_unity_menu_tag = 1

    def _unity_menu_tag(self, hwnd):
        tag = self._unity_menu_tags.get(hwnd)
        if tag is None:
            tag = self._next_unity_menu_tag
            self._next_unity_menu_tag += 1
            self._unity_menu_tags[hwnd] = tag
        return tag

    @staticmethod
    def _window_launch_order(hwnd):
        """Use process creation time to make initial menu tags reproducible."""
        process_handle = None
        try:
            _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
            process_handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION, False, process_id
            )
            creation_time = win32process.GetProcessTimes(process_handle)["CreationTime"]
            if hasattr(creation_time, "timestamp"):
                creation_time = creation_time.timestamp()
            return float(creation_time), int(hwnd)
        except Exception:
            return 0.0, int(hwnd)
        finally:
            if process_handle:
                try:
                    win32api.CloseHandle(process_handle)
                except Exception:
                    pass

    def matches_current_game_window(self, hwnd, title=None):
        """Return whether a visible HWND belongs to the selected game engine."""
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return False
            title = win32gui.GetWindowText(hwnd) if title is None else title
            if not title.strip():
                return False
            game_version = self.config.data.get("game_version", "Unity")
            if game_version == "Unity":
                return win32gui.GetClassName(hwnd) == "UnityWndClass"
            if game_version == "Rétro":
                process_name = get_window_process_name(hwnd)
                if process_name and "dofus" not in process_name:
                    return False
                return bool(
                    RETRO_CHARACTER_TITLE.match(title) or RETRO_LOADING_TITLE.match(title)
                )
            if game_version == "Wakfu":
                return is_wakfu_window(hwnd, title, win32gui.GetClassName(hwnd))
        except Exception:
            pass
        return False

    def has_target_game_window(self):
        """Cheap detector used by the automatic refresh watchdog."""
        found = False

        def enum_windows_callback(hwnd, _extra):
            nonlocal found
            if self.matches_current_game_window(hwnd):
                found = True
                return False
            return True

        try:
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception:
            pass
        return found

    def scan_slots(self):
        game_version = self.config.data.get("game_version", "Unity")
        windows_trouvees = []

        def enum_windows_callback(hwnd, extra):
            titre = win32gui.GetWindowText(hwnd)
            if self.matches_current_game_window(hwnd, titre):
                windows_trouvees.append((hwnd, titre))
            return True

        win32gui.EnumWindows(enum_windows_callback, None)

        if game_version == "Unity":
            # Assign tags in launch order, not in the unstable z-order returned
            # by EnumWindows. Keep tags even when a HWND temporarily acquires a
            # character title, and remove them only after the window closes.
            windows_trouvees.sort(key=lambda item: self._window_launch_order(item[0]))
            self._prune_unity_menu_tags(hwnd for hwnd, _title in windows_trouvees)

        nouveaux_comptes = []
        menu_counter = 1 # Compteur pour différencier les fenêtres sans perso

        for hwnd, titre in windows_trouvees:
            titre_clean = titre.strip()
            is_menu = False
            
            if game_version == "Unity":
                # Si le titre commence par "dofus" (ex: "Dofus", "Dofus 3.0"), c'est souvent la page de connexion sans perso
                if titre_clean.lower().startswith("dofus"): 
                    menu_tag_index = self._unity_menu_tag(hwnd)
                    loop_tag = f"U{menu_tag_index}"
                    pseudo = f"Menu Unity [{loop_tag}]"
                    classe = "Inconnu"
                    is_menu = True
                    menu_counter += 1
                else:
                    parts = titre_clean.split(" - ")
                    pseudo = parts[0].strip()
                    classe = parts[1].strip() if len(parts) > 1 else "Inconnu"
            elif game_version == "Rétro":
                retro_match = RETRO_CHARACTER_TITLE.match(titre_clean)
                if retro_match is None:
                    pseudo = f"Menu Rétro {menu_counter}"
                    classe = "Inconnu"
                    is_menu = True
                    menu_counter += 1
                else:
                    pseudo = retro_match.group("pseudo").strip()
                    classe = self.config.data["classes"].get(pseudo, "Inconnu")
            else:
                # WAKFU tourne en Java. Une page de jeu porte `PSEUDO - WAKFU`.
                pseudo = get_wakfu_character_name(titre_clean)
                if pseudo is None:
                    pseudo = f"Menu Wakfu {menu_counter}"
                    classe = "Inconnu"
                    is_menu = True
                    menu_counter += 1
                else:
                    classe = self.config.data["classes"].get(pseudo, "Inconnu")
                
            self.config.data["classes"][pseudo] = classe
            etat_actif = self.config.data["accounts_state"].get(pseudo, True)
            equipe = self.config.data["accounts_team"].get(pseudo, "Team 1")
            
            # On ajoute la clé "is_menu" pour indiquer à l'UI que c'est une page de connexion
            nouveaux_comptes.append({
                'name': pseudo, 'hwnd': hwnd, 'active': etat_actif,
                'team': equipe, 'classe': classe, 'is_menu': is_menu,
                'loop_tag': loop_tag if game_version == "Unity" and is_menu else "",
                'loop_tag_index': menu_tag_index if game_version == "Unity" and is_menu else None,
            })

        custom_order = self.config.data.get("custom_order", [])
        
        for acc in nouveaux_comptes:
            if acc['name'] not in custom_order:
                custom_order.append(acc['name'])
                
        if len(custom_order) > 50:
            active_names = [acc['name'] for acc in nouveaux_comptes]
            inactive = [n for n in custom_order if n not in active_names]
            while len(custom_order) > 50 and inactive:
                to_remove = inactive.pop(0)
                if to_remove in custom_order:
                    custom_order.remove(to_remove)
                    
        self.config.data["custom_order"] = custom_order
        self.config.save()
        
        def account_order(account):
            # Connected characters keep the user's custom initiative order.
            # Unidentified Unity clients rotate after them in their stable U-tag order.
            menu_tag = account.get("loop_tag_index")
            if menu_tag is not None:
                return 1, menu_tag
            return 0, custom_order.index(account['name'])

        self.all_accounts = sorted(nouveaux_comptes, key=account_order)
        
        self.leader_hwnd = None
        leader_name = self.config.data.get("leader_name", "")
        for acc in self.all_accounts:
            if acc['name'] == leader_name: self.leader_hwnd = acc['hwnd']
                
        return self.all_accounts

    def focused_account_identity_changed(self, hwnd):
        """Cheaply detect a renamed/login client without rescanning every window.

        Page switching is latency-sensitive.  A full ``scan_slots`` also saves
        the complete configuration, so doing it from the focus callback made
        every shortcut wait on window enumeration and disk I/O.  Reading the
        title of the one window being focused is enough to decide whether a
        later full refresh is actually necessary.
        """
        account = next(
            (candidate for candidate in self.all_accounts if candidate.get("hwnd") == hwnd),
            None,
        )
        if account is None:
            return True
        try:
            title = win32gui.GetWindowText(hwnd).strip()
            if not self.matches_current_game_window(hwnd, title):
                return False
        except Exception:
            return False

        game_version = self.config.data.get("game_version", "Unity")
        if game_version == "Unity":
            is_menu = title.casefold().startswith("dofus")
            name = "" if is_menu else title.split(" - ", 1)[0].strip()
        elif game_version == "Rétro":
            match = RETRO_CHARACTER_TITLE.match(title)
            is_menu = match is None
            name = "" if is_menu else match.group("pseudo").strip()
        else:
            name = get_wakfu_character_name(title) or ""
            is_menu = not bool(name)

        return (
            bool(account.get("is_menu", False)) != is_menu
            or (not is_menu and account.get("name") != name)
        )

    def get_cycle_list(self):
        mode = self.config.data.get("current_mode", "ALL")
        return [acc for acc in self.all_accounts if acc['active'] and (mode == "ALL" or acc['team'] == mode)]

    def _update_global_order_from_active(self, active_accs):
        order = self.config.data.get("custom_order", [])
        indices = []
        valid_names = []
        for acc in active_accs:
            if acc['name'] in order:
                indices.append(order.index(acc['name']))
                valid_names.append(acc['name'])
                
        indices.sort()
        for i, name in zip(indices, valid_names):
            order[i] = name
            
        self.config.data["custom_order"] = order
        self.config.save()
        self.all_accounts.sort(key=lambda x: order.index(x['name']))

    def set_account_position(self, name, new_index):
        active_accs = self.get_cycle_list()
        names = [a['name'] for a in active_accs]
        if name not in names: return
        idx = names.index(name)
        acc_to_move = active_accs.pop(idx)
        active_accs.insert(new_index, acc_to_move)
        self._update_global_order_from_active(active_accs)

    def move_account(self, name, direction):
        active_accs = self.get_cycle_list()
        names = [a['name'] for a in active_accs]
        if name not in names: return
        idx = names.index(name)
        new_idx = idx + direction
        if 0 <= new_idx < len(names):
            active_accs[idx], active_accs[new_idx] = active_accs[new_idx], active_accs[idx]
            self._update_global_order_from_active(active_accs)

    def toggle_account(self, name, is_active):
        for acc in self.all_accounts:
            if acc['name'] == name: acc['active'] = is_active
        self.config.data["accounts_state"][name] = is_active
        self.config.save()

    def change_team(self, name, new_team):
        for acc in self.all_accounts:
            if acc['name'] == name: acc['team'] = new_team
        self.config.data["accounts_team"][name] = new_team
        self.config.save()

    def set_mode(self, mode):
        self.config.data["current_mode"] = mode
        self.config.save()

    def set_leader(self, name):
        self.leader_hwnd = None
        self.config.data["leader_name"] = name
        self.config.save()
        for acc in self.all_accounts:
            if acc['name'] == name: self.leader_hwnd = acc['hwnd']

    def close_account_window(self, name):
        for acc in self.all_accounts:
            if acc['name'] == name:
                hwnd = acc['hwnd']
                try:
                    if not win32gui.IsWindow(hwnd):
                        return False
                    # Ask the client to close normally so it can flush its own
                    # settings. Never terminate a game process from the UI.
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    return True
                except Exception:
                    return False
        return False

    def close_all_active_accounts(self):
        active_accs = self.get_cycle_list()
        requested = 0
        for acc in active_accs:
            hwnd = acc['hwnd']
            try:
                if win32gui.IsWindow(hwnd):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    requested += 1
            except Exception:
                pass
        return requested

    def focus_window(self, hwnd):
        if not hwnd:
            self.last_focus_debug = "missing_hwnd"
            return False
        try:
            if not win32gui.IsWindow(hwnd):
                self.last_focus_debug = f"invalid_hwnd:{hwnd!r}"
                return False
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)

            # Inspired by Dracoon (Slyss42, MIT): never synthesize Alt or a
            # mouse input to bypass Windows' foreground protection. Synthetic
            # key transitions can remain logically pressed if focus changes at
            # the wrong instant. SetForegroundWindow already raises and
            # activates the target; calling BringWindowToTop first duplicated
            # the activation messages received by Unity.
            # If Windows silently refuses the direct request, retain the
            # previously proven short-lived AttachThreadInput fallback. It is
            # detached in a finally block before integrations are notified.
            strategy = "direct"
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                strategy = "attach_thread_input"
                if not self._attach_and_set_foreground(hwnd):
                    self.last_focus_debug = f"focus_refused:pid={pid}"
                    return False

            focused = win32gui.GetForegroundWindow() == hwnd
            if not focused and strategy == "direct":
                strategy = "attach_thread_input"
                focused = self._attach_and_set_foreground(hwnd)
                focused = focused and win32gui.GetForegroundWindow() == hwnd
            if not focused:
                self.last_focus_debug = f"focus_not_confirmed:strategy={strategy}:pid={pid}"
                return False

            self.last_focus_debug = f"focus_confirmed:strategy={strategy}:pid={pid}"
            if self.on_window_focused:
                self.on_window_focused(hwnd)
            return True
        except Exception as exc:
            self.last_focus_debug = f"{type(exc).__name__}:{exc!s:.180}"
            return False

    @staticmethod
    def _attach_and_set_foreground(hwnd):
        """Temporarily join input queues; always detach them before returning."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        foreground = win32gui.GetForegroundWindow()
        current_tid = kernel32.GetCurrentThreadId()
        foreground_tid = win32process.GetWindowThreadProcessId(foreground)[0] if foreground else 0
        target_tid = win32process.GetWindowThreadProcessId(hwnd)[0]
        attached_foreground = False
        attached_target = False
        try:
            if foreground_tid and foreground_tid != current_tid:
                attached_foreground = bool(
                    user32.AttachThreadInput(current_tid, foreground_tid, True)
                )
            if target_tid and target_tid not in (current_tid, foreground_tid):
                attached_target = bool(
                    user32.AttachThreadInput(current_tid, target_tid, True)
                )
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False
        finally:
            if attached_target:
                user32.AttachThreadInput(current_tid, target_tid, False)
            if attached_foreground:
                user32.AttachThreadInput(current_tid, foreground_tid, False)

    def sort_taskbar(self):
        active_accs = self.get_cycle_list()
        if not active_accs: return
        try:
            for acc in active_accs:
                win32gui.ShowWindow(acc['hwnd'], win32con.SW_HIDE)
            time.sleep(0.3)
            for acc in active_accs:
                win32gui.ShowWindow(acc['hwnd'], win32con.SW_SHOW)
                time.sleep(0.1) 
            if self.leader_hwnd:
                self.focus_window(self.leader_hwnd)
        except Exception: pass

    def _retro_layout_windows(self):
        """Return every detected Retro client in DOSOFT's explicit order."""
        if self.config.data.get("game_version") != "Rétro":
            return []
        # A fresh scan includes newly opened clients and excludes stale HWNDs.
        accounts = self.scan_slots()
        return [
            account for account in accounts
            if account.get("hwnd") and win32gui.IsWindow(account["hwnd"])
        ]

    def maximize_retro_windows(self):
        accounts = self._retro_layout_windows()
        return maximize_windows(account["hwnd"] for account in accounts)

    def tile_retro_windows(self):
        accounts = self._retro_layout_windows()
        anchor = self.leader_hwnd or (accounts[0]["hwnd"] if accounts else None)
        return tile_windows(
            (account["hwnd"] for account in accounts),
            anchor_hwnd=anchor,
            max_columns=4,
        )

    def execute_advanced_bind(self, source, identifier):
        """ Gère le focus dynamique et retourne le nouvel index pour la boucle. """
        active_list = self.get_cycle_list()
        if not active_list: return -1

        target_hwnd = None
        new_global_idx = -1

        if source == "cycle":
            row_index = int(identifier)
            if row_index < len(active_list):
                target_hwnd = active_list[row_index]['hwnd']
                new_global_idx = row_index

        elif source == "bind":
            target_pseudo = str(identifier)
            for index, acc in enumerate(active_list):
                if acc['name'] == target_pseudo:
                    target_hwnd = acc['hwnd']
                    new_global_idx = index
                    break
        
        if target_hwnd:
            self.focus_window(target_hwnd)
            return new_global_idx 
        return -1
