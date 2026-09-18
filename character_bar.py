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

    def __init__(self, parent_root, config, on_character_selected, on_visibility_changed):
        self.parent_root = parent_root
        self.config = config
        self.on_character_selected = on_character_selected
        self.on_visibility_changed = on_visibility_changed
        self.accounts = []
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
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.hide_from_bar)

        # Default CustomTkinter frames request 200 px.  A tiny base width lets
        # the vertical layout contract to the portraits instead.
        self.outer = ctk.CTkFrame(self.window, width=1, corner_radius=14, border_width=1)
        self.outer.pack(padx=1, pady=1)

        self.handle = ctk.CTkFrame(self.outer, height=25, corner_radius=10)
        self.handle.pack(fill="x", padx=5, pady=(5, 2))
        self.handle.pack_propagate(False)
        self.cross_image = self.load_menu_icon("croix.png")
        self.up_image = self.load_menu_icon("up.png")
        self.orientation_button = ctk.CTkButton(
            self.handle, text="", image=self.up_image, width=24, height=20,
            corner_radius=7, command=self.toggle_orientation,
        )
        self.orientation_button.pack(side="right", padx=(2, 3), pady=2)
        self.hide_button = ctk.CTkButton(
            self.handle, text="", image=self.cross_image, width=24, height=20, corner_radius=7,
            command=self.hide_from_bar,
        )
        self.hide_button.pack(side="right", padx=3, pady=2)
        for widget in (self.handle,):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.drag)
            widget.bind("<ButtonRelease-1>", self.end_drag)

        self.content = ctk.CTkFrame(self.outer, width=1, fg_color="transparent")
        self.content.pack(padx=5, pady=(1, 5))
        self.parent_root.after(250, self.poll_active_window)

    def update_theme(self, theme, engine):
        self.theme = dict(theme)
        self.engine = engine
        self.rebuild()

    def update_accounts(self, accounts, engine):
        self.engine = engine
        self.accounts = list(accounts)
        self.rebuild()
        if self.config.data.get("character_bar_visible", False):
            self.set_visible(True)

    def set_visible(self, visible):
        if not visible:
            self.window.withdraw()
            return
        self.rebuild()
        self.position_window()
        self.window.deiconify()
        self.window.lift()
        self.window.attributes("-topmost", True)

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

    def end_drag(self, _event):
        self._drag_origin = None
        self.config.data["character_bar_position"] = [self.window.winfo_x(), self.window.winfo_y()]
        self.config.save()

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
        self.window.configure(fg_color=theme.get("background", panel))
        self.outer.configure(fg_color=panel, border_color=border)
        self.handle.configure(fg_color=panel_alt)
        self.hide_button.configure(fg_color=theme.get("clear", "#a3434d"), hover_color=theme.get("clear_hover", "#c95862"))
        self.orientation_button.configure(
            fg_color=accent if self.var_vertical.get() else panel,
            hover_color=theme.get("accent_hover", accent),
            border_width=1 if self.var_vertical.get() else 0,
            border_color=border if self.var_vertical.get() else panel,
        )

        if not self.accounts:
            ctk.CTkLabel(self.content, text="Aucun personnage détecté", text_color=muted).pack(padx=12, pady=7)
            self.reanchor_after_resize(was_visible, old_x, old_y, old_width, old_height)
            return

        # Up to 14 characters keep the intended generous spacing.  Above that,
        # cards contract slightly so every detected account remains available.
        total = len(self.accounts)
        is_vertical = self.var_vertical.get()
        card_width = 47 if total <= self.MAX_COMFORTABLE_CELLS else max(38, 658 // total)
        for account in self.accounts:
            card = ctk.CTkButton(
                self.content,
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

    def poll_active_window(self):
        try:
            foreground = win32gui.GetForegroundWindow()
            theme = self.theme
            for button, account in self.cards:
                active = account.get("hwnd") == foreground
                button.configure(
                    fg_color=theme.get("accent", "#2f80c3") if active else theme.get("panel_alt", "#34495e"),
                    border_color=theme.get("border", "#78b9e8") if active else theme.get("panel_alt", "#34495e"),
                    border_width=2 if active else 1,
                )
        except (tk.TclError, Exception):
            pass
        finally:
            try:
                self.parent_root.after(250, self.poll_active_window)
            except tk.TclError:
                pass
