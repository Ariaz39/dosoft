"""Always-on-top quick character switcher shared by every DOSOFT engine."""

from __future__ import annotations

import os
import tkinter as tk

import customtkinter as ctk
import win32gui
from PIL import Image

from resource_paths import resource_path, skin_path


class CharacterQuickBar:
    """A compact, draggable bar of detected characters.

    The parent application owns detection and focus.  This widget only renders
    the current accounts and reports a click back to the application.
    """

    MAX_COMFORTABLE_CELLS = 14

    def __init__(self, parent_root, config, on_character_selected, on_visibility_changed, on_team_selected):
        self.parent_root = parent_root
        self.config = config
        self.on_character_selected = on_character_selected
        self.on_visibility_changed = on_visibility_changed
        self.on_team_selected = on_team_selected
        self.accounts = []
        self.ghost_accounts = []
        self.ghost_team = None
        self.engine = config.data.get("game_version", "Unity")
        self.theme = {}
        self.image_cache = {}
        self.cards = []
        self._drag_origin = None
        self.var_vertical = ctk.BooleanVar(value=config.data.get("character_bar_vertical", False))

        self.window = ctk.CTkToplevel(parent_root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.transparent_color = "#0b0b0b"
        try:
            self.window.configure(fg_color=self.transparent_color)
            self.window.attributes("-transparentcolor", self.transparent_color)
        except tk.TclError:
            pass
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.hide_from_bar)

        # This is a complete, deliberately faded second bar.  It stays behind
        # the primary bar and serves as one-click access to the other team.
        self.ghost_window = ctk.CTkToplevel(parent_root)
        self.ghost_window.withdraw()
        self.ghost_window.overrideredirect(True)
        self.ghost_window.attributes("-topmost", True)
        try:
            self.ghost_window.configure(fg_color=self.transparent_color)
            self.ghost_window.attributes("-transparentcolor", self.transparent_color)
            self.ghost_window.attributes("-alpha", 0.46)
        except tk.TclError:
            pass
        self.ghost_window.resizable(False, False)

        # Default CustomTkinter frames request 200 px.  A tiny base width lets
        # the vertical layout contract to the portraits instead.
        self.outer = ctk.CTkFrame(self.window, width=1, corner_radius=14, border_width=1)
        self.outer.pack(padx=1, pady=1)
        self.ghost_outer = ctk.CTkFrame(self.ghost_window, width=1, corner_radius=14, border_width=1)
        self.ghost_outer.pack(padx=1, pady=1)

        self.cross_image = self.load_menu_icon("croix.png")
        self.up_image = self.load_menu_icon("up.png")
        self.content = ctk.CTkFrame(self.outer, width=1, fg_color="transparent")
        self.content.pack(padx=5, pady=5)
        self.ghost_content = ctk.CTkFrame(self.ghost_outer, width=1, fg_color="transparent")
        self.ghost_content.pack(padx=5, pady=5)
        self.parent_root.after(250, self.poll_active_window)

    def update_theme(self, theme, engine):
        self.theme = dict(theme)
        self.engine = engine
        self.rebuild()

    def update_accounts(self, accounts, engine):
        self.engine = engine
        active_accounts = [account for account in accounts if account.get("active", False)]
        mode = self.config.data.get("current_mode", "ALL")
        if mode in ("Team 1", "Team 2"):
            self.accounts = [account for account in active_accounts if account.get("team") == mode]
            self.ghost_accounts = [] if self.config.data.get("fast_switch_team_disabled", False) else [
                account for account in active_accounts if account.get("team") != mode
            ]
            self.ghost_team = self.ghost_accounts[0].get("team") if self.ghost_accounts else None
        else:
            self.accounts = active_accounts
            self.ghost_accounts = []
            self.ghost_team = None
        self.rebuild()
        if self.config.data.get("character_bar_visible", False):
            self.set_visible(True)

    def set_visible(self, visible):
        if not visible:
            self.window.withdraw()
            self.ghost_window.withdraw()
            return
        self.rebuild()
        self.position_window()
        self.window.deiconify()
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.sync_ghost_bar()

    def hide_from_bar(self):
        self.on_visibility_changed(False)

    def toggle_orientation(self):
        self.var_vertical.set(not self.var_vertical.get())
        self.config.data["character_bar_vertical"] = self.var_vertical.get()
        self.config.save()
        self.rebuild()

    @staticmethod
    def load_menu_icon(filename):
        path = resource_path("resources", "skin", "icone menu", filename)
        try:
            image = Image.open(path)
            return ctk.CTkImage(light_image=image, dark_image=image, size=(14, 14))
        except Exception:
            return None

    def position_window(self):
        saved = self.config.data.get("character_bar_position", [])
        if isinstance(saved, list) and len(saved) == 2:
            x_pos, y_pos = (int(saved[0]), int(saved[1]))
        else:
            self.window.update_idletasks()
            x_pos = max(10, (self.window.winfo_screenwidth() - self.window.winfo_width()) // 2)
            y_pos = 20
        self.window.geometry(f"+{x_pos}+{y_pos}")

    def start_drag(self, event):
        self._drag_origin = (event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())

    def drag(self, event):
        if not self._drag_origin:
            return
        mouse_x, mouse_y, window_x, window_y = self._drag_origin
        self.window.geometry(f"+{window_x + event.x_root - mouse_x}+{window_y + event.y_root - mouse_y}")
        self.sync_ghost_bar()

    def end_drag(self, _event):
        self._drag_origin = None
        self.config.data["character_bar_position"] = [self.window.winfo_x(), self.window.winfo_y()]
        self.config.save()
        self.sync_ghost_bar()

    def image_for(self, class_name):
        class_filename = (class_name or "Inconnu").removesuffix("_retro").lower()
        quick_icon = resource_path("resources", "skin", "icone menu", f"eco_{class_filename}.png")
        engine = "retro" if self.engine == "Rétro" else "wakfu" if self.engine == "Wakfu" else "unity"
        path = quick_icon if os.path.exists(quick_icon) else skin_path(class_name, engine=engine)
        cache_key = f"quickbar:{path}"
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]
        try:
            image = Image.open(path)
            result = ctk.CTkImage(light_image=image, dark_image=image, size=(30, 30))
            self.image_cache[cache_key] = result
            return result
        except Exception:
            return None

    def is_on_right_half(self):
        saved = self.config.data.get("character_bar_position", [])
        x_pos = saved[0] if isinstance(saved, list) and len(saved) == 2 else self.window.winfo_x()
        return x_pos + self.window.winfo_width() / 2 > self.window.winfo_screenwidth() / 2

    def create_controls(self, parent, theme):
        """Create an icon-only compact control strip with a small drag grip."""
        panel = theme.get("panel", "#283845")
        accent = theme.get("accent", "#2f80c3")
        border = theme.get("border", "#78b9e8")
        controls = ctk.CTkFrame(parent, width=1, height=46, corner_radius=10, fg_color=panel)
        drag_grip = ctk.CTkFrame(controls, width=6, height=28, corner_radius=3, fg_color=theme.get("panel_alt", panel))
        drag_grip.pack(side="left", padx=(4, 2), pady=9)
        for widget in (drag_grip,):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.drag)
            widget.bind("<ButtonRelease-1>", self.end_drag)
        self.hide_button = ctk.CTkButton(
            controls, text="", image=self.cross_image, width=24, height=22, corner_radius=7,
            fg_color=theme.get("clear", "#a3434d"), hover_color=theme.get("clear_hover", "#c95862"),
            command=self.hide_from_bar,
        )
        self.hide_button.pack(side="left", padx=2, pady=10)
        self.orientation_button = ctk.CTkButton(
            controls, text="", image=self.up_image, width=24, height=22, corner_radius=7,
            fg_color=accent if self.var_vertical.get() else panel,
            hover_color=theme.get("accent_hover", accent),
            border_width=1 if self.var_vertical.get() else 0,
            border_color=border if self.var_vertical.get() else panel,
            command=self.toggle_orientation,
        )
        self.orientation_button.pack(side="left", padx=(2, 4), pady=10)
        return controls

    def rebuild(self):
        if not self.theme:
            return
        was_visible = self.window.winfo_viewable()
        old_x, old_y = self.window.winfo_x(), self.window.winfo_y()
        old_width, old_height = self.window.winfo_width(), self.window.winfo_height()
        for widget in self.content.winfo_children():
            widget.destroy()
        self.cards.clear()

        theme = self.theme
        panel = theme.get("panel", "#283845")
        panel_alt = theme.get("panel_alt", "#34495e")
        accent = theme.get("accent", "#2f80c3")
        border = theme.get("border", "#78b9e8")
        title = theme.get("title", "#ecf0f1")
        muted = theme.get("muted", "#b7c9d6")
        self.outer.configure(fg_color=panel, border_color=border)
        is_vertical = self.var_vertical.get()
        controls = self.create_controls(self.content, theme)
        cards_frame = ctk.CTkFrame(self.content, width=1, fg_color="transparent")
        if is_vertical:
            controls.pack(side="top", anchor="center", pady=(0, 3))
            cards_frame.pack(side="top", anchor="center")
        elif self.is_on_right_half():
            controls.pack(side="left", pady=2)
            cards_frame.pack(side="left")
        else:
            cards_frame.pack(side="left")
            controls.pack(side="right", pady=2)

        if not self.accounts:
            ctk.CTkLabel(cards_frame, text="Aucun personnage détecté", text_color=muted).pack(padx=12, pady=7)
            self.reanchor_after_resize(was_visible, old_x, old_y, old_width, old_height)
            self.rebuild_ghost_bar()
            return

        # Up to 14 characters keep the intended generous spacing.  Above that,
        # cards contract slightly so every detected account remains available.
        total = len(self.accounts)
        card_width = 47 if total <= self.MAX_COMFORTABLE_CELLS else max(38, 658 // total)
        for account in self.accounts:
            card = ctk.CTkButton(
                cards_frame,
                text="",
                image=self.image_for(account.get("classe", "Inconnu")),
                width=card_width,
                height=46,
                corner_radius=10,
                fg_color=panel_alt,
                hover_color=accent,
                border_width=1,
                border_color=panel_alt,
                command=lambda selected=account: self.on_character_selected(selected),
            )
            card.pack(side="top" if is_vertical else "left", padx=2, pady=2)
            card.bind("<Enter>", lambda _event, button=card: button.configure(border_color=border))
            card.bind("<Leave>", lambda _event, button=card: button.configure(border_color=panel_alt))
            self.cards.append((card, account))
        self.reanchor_after_resize(was_visible, old_x, old_y, old_width, old_height)
        self.rebuild_ghost_bar()
        self.update_card_states()

    def reanchor_after_resize(self, was_visible, old_x, old_y, old_width, old_height):
        """Keep the nearest screen edge fixed while the bar gains cards."""
        self.window.update_idletasks()
        if not was_visible:
            return
        new_width, new_height = self.window.winfo_width(), self.window.winfo_height()
        screen_width, screen_height = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        anchor_right = old_x + old_width / 2 > screen_width / 2
        anchor_bottom = old_y + old_height / 2 > screen_height / 2
        new_x = old_x + old_width - new_width if anchor_right else old_x
        new_y = old_y + old_height - new_height if anchor_bottom else old_y
        new_x = max(0, min(new_x, screen_width - new_width))
        new_y = max(0, min(new_y, screen_height - new_height))
        self.window.geometry(f"+{new_x}+{new_y}")
        self.config.data["character_bar_position"] = [new_x, new_y]
        self.config.save()
        self.sync_ghost_bar()

    def rebuild_ghost_bar(self):
        """Render the inactive team in its own reduced-opacity window."""
        for widget in self.ghost_content.winfo_children():
            widget.destroy()
        if not self.ghost_team or not self.ghost_accounts:
            self.ghost_window.withdraw()
            return

        theme = self.theme
        panel_alt = theme.get("panel_alt", "#34495e")
        self.ghost_outer.configure(
            fg_color=theme.get("panel", "#283845"),
            border_color=theme.get("border", "#78b9e8"),
        )
        is_vertical = self.var_vertical.get()
        cards_frame = ctk.CTkFrame(self.ghost_content, width=1, fg_color="transparent")
        cards_frame.pack()
        total = len(self.ghost_accounts)
        card_width = 47 if total <= self.MAX_COMFORTABLE_CELLS else max(38, 658 // total)
        for account in self.ghost_accounts:
            card = ctk.CTkButton(
                cards_frame, text="", image=self.image_for(account.get("classe", "Inconnu")),
                width=card_width, height=46, corner_radius=10,
                fg_color=panel_alt, hover_color=theme.get("accent", "#2f80c3"),
                border_width=1, border_color=panel_alt,
                command=lambda team=self.ghost_team: self.on_team_selected(team),
            )
            card.pack(side="top" if is_vertical else "left", padx=2, pady=2)
        self.ghost_window.update_idletasks()
        self.sync_ghost_bar()

    def sync_ghost_bar(self):
        """Place the ghost under, and offset by half, the main quick bar."""
        if not self.ghost_team or not self.ghost_accounts or not self.window.winfo_viewable():
            self.ghost_window.withdraw()
            return
        self.window.update_idletasks()
        self.ghost_window.update_idletasks()
        main_x, main_y = self.window.winfo_x(), self.window.winfo_y()
        main_w, main_h = self.window.winfo_width(), self.window.winfo_height()
        ghost_w, ghost_h = self.ghost_window.winfo_width(), self.ghost_window.winfo_height()
        if self.var_vertical.get():
            to_right = main_x + main_w / 2 < self.window.winfo_screenwidth() / 2
            ghost_x = main_x + main_w // 2 if to_right else main_x - ghost_w + main_w // 2
            ghost_y = main_y
        else:
            below = main_y + main_h / 2 < self.window.winfo_screenheight() / 2
            ghost_x = main_x
            ghost_y = main_y + main_h // 2 if below else main_y - ghost_h + main_h // 2
        self.ghost_window.geometry(f"+{int(ghost_x)}+{int(ghost_y)}")
        self.ghost_window.deiconify()
        self.ghost_window.lift()
        self.window.lift()
        self.window.attributes("-topmost", True)

    def update_card_states(self):
        try:
            foreground = win32gui.GetForegroundWindow()
        except Exception:
            foreground = 0
        theme = self.theme
        leader_name = self.config.data.get("leader_name", "")
        gold = "#e5bd5d"
        for button, account in self.cards:
            active = account.get("hwnd") == foreground
            is_leader = account.get("name") == leader_name
            button.configure(
                fg_color=theme.get("accent", "#2f80c3") if active else theme.get("panel_alt", "#34495e"),
                border_color=gold if is_leader else theme.get("border", "#78b9e8") if active else theme.get("panel_alt", "#34495e"),
                border_width=2 if is_leader or active else 1,
            )

    def poll_active_window(self):
        try:
            self.update_card_states()
        except (tk.TclError, Exception):
            pass
        finally:
            try:
                self.parent_root.after(250, self.poll_active_window)
            except tk.TclError:
                pass
