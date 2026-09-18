"""Always-on-top quick character switcher shared by every DOSOFT engine."""

from __future__ import annotations

import os
import tkinter as tk
import ctypes
from datetime import datetime

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
        self._last_foreground = None
        self._last_observed_foreground = None
        self._selected_hwnd = 0
        self._color_transition_token = 0
        self._render_signature = None
        self._pending_signature = None
        self._layout_transition_token = 0
        self._transitioning = False
        self._pending_foreground = 0
        self._shape_sizes = {}
        self._ghost_switch_locked = False
        self.debug_path = os.environ.get(
            "DOSOFT_QUICKBAR_DEBUG_LOG",
            os.path.join(os.path.dirname(os.path.abspath(config.filename)), "quickbar-debug.log"),
        )
        self.var_vertical = ctk.BooleanVar(value=config.data.get("character_bar_vertical", False))

        self.window = ctk.CTkToplevel(parent_root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.hide_from_bar)

        # This is a complete, deliberately faded second bar.  It stays behind
        # the primary bar and serves as one-click access to the other team.
        self.ghost_window = ctk.CTkToplevel(parent_root)
        self.ghost_window.withdraw()
        self.ghost_window.overrideredirect(True)
        self.ghost_window.attributes("-topmost", True)
        try:
            self.ghost_window.attributes("-alpha", 0.58)
        except tk.TclError:
            pass
        self.ghost_window.resizable(False, False)
        self.parent_root.after_idle(self.make_ghost_non_activating)

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
        self.debug("initialisation")

    def debug(self, message):
        """Append quick-bar diagnostics to the isolated beta-data folder."""
        try:
            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            with open(self.debug_path, "a", encoding="utf-8") as log:
                log.write(f"[{stamp}] {message}\n")
        except OSError:
            pass

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
        signature = self.display_signature()
        if signature != self._render_signature:
            self.request_layout_refresh(signature)
        if self.config.data.get("character_bar_visible", False):
            self.set_visible(True)

    def display_signature(self):
        """Stable render identity: unchanged scans must not redraw the bar."""
        account_fields = lambda accounts: tuple(
            (account.get("name"), account.get("hwnd"), account.get("classe"), account.get("team"))
            for account in accounts
        )
        return (
            self.engine,
            self.var_vertical.get(),
            account_fields(self.accounts),
            self.ghost_team,
            account_fields(self.ghost_accounts),
        )

    def request_layout_refresh(self, signature):
        """Fade existing cards before applying a different ordering/list."""
        if self._pending_signature == signature:
            return
        if not self.window.winfo_viewable() or not self.cards:
            self.rebuild()
            self._render_signature = signature
            self._pending_signature = None
            return
        self._pending_signature = signature
        self._layout_transition_token += 1
        token = self._layout_transition_token
        self.debug("disposition: transition demandée")
        for step in range(4):
            self.parent_root.after(
                step * 26,
                lambda progress=step / 3, current=token: self.fade_layout_cards(progress, current),
            )
        self.parent_root.after(104, lambda current=token: self.finish_layout_refresh(current))

    def fade_layout_cards(self, progress, token):
        if token != self._layout_transition_token:
            return
        panel = self.theme.get("panel", "#283845")
        panel_alt = self.theme.get("panel_alt", "#34495e")
        for button, _account in self.cards:
            button.configure(
                fg_color=self.blend_color(panel_alt, panel, progress),
                border_color=self.blend_color(panel_alt, panel, progress),
            )

    def finish_layout_refresh(self, token):
        if token != self._layout_transition_token:
            return
        self.rebuild()
        self._render_signature = self._pending_signature
        self._pending_signature = None
        self.debug("disposition: transition appliquée")

    def set_visible(self, visible):
        if not visible:
            self.window.withdraw()
            self.ghost_window.withdraw()
            return
        signature = self.display_signature()
        if signature != self._render_signature and self._pending_signature is None:
            self.rebuild()
            self._render_signature = signature
        self.position_window()
        self.window.deiconify()
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.apply_rounded_shape(self.window)
        self.sync_ghost_bar()

    def hide_from_bar(self):
        self.on_visibility_changed(False)

    def toggle_orientation(self):
        self.var_vertical.set(not self.var_vertical.get())
        self.config.data["character_bar_vertical"] = self.var_vertical.get()
        self.config.save()
        self.request_layout_refresh(self.display_signature())

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
        self.debug(f"drag:start x={self.window.winfo_x()} y={self.window.winfo_y()}")
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
        self.debug(f"drag:end x={self.window.winfo_x()} y={self.window.winfo_y()}")

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
        self.window.configure(fg_color=panel)
        is_vertical = self.var_vertical.get()
        controls = self.create_controls(self.content, theme)
        # Keep the inactive team portraits exactly on the same axis as the
        # active portraits, despite the latter's control strip.
        self.ghost_control_space = 78
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
            self.fit_window_to_content(self.window, self.outer)
            self.reanchor_after_resize(was_visible, old_x, old_y, old_width, old_height)
            self.window.update_idletasks()
            self.apply_rounded_shape(self.window)
            self.ghost_control_space = controls.winfo_width()
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
        self.fit_window_to_content(self.window, self.outer)
        self.reanchor_after_resize(was_visible, old_x, old_y, old_width, old_height)
        self.window.update_idletasks()
        self.apply_rounded_shape(self.window)
        self.ghost_control_space = controls.winfo_width()
        self.rebuild_ghost_bar()
        self._last_foreground = None
        self._selected_hwnd = 0
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
        self.ghost_window.configure(fg_color=theme.get("panel", "#283845"))
        for widget in (self.ghost_outer, self.ghost_content):
            widget.bind("<Button-1>", self.select_ghost_team)
            widget.bind("<ButtonPress-1>", lambda _event: self.keep_ghost_below_main())
        is_vertical = self.var_vertical.get()
        cards_frame = ctk.CTkFrame(self.ghost_content, width=1, fg_color="transparent")
        cards_frame.bind("<Button-1>", self.select_ghost_team)
        spacer = ctk.CTkFrame(self.ghost_content, fg_color="transparent")
        if is_vertical:
            spacer.configure(width=1, height=49)
            spacer.pack(side="top")
            cards_frame.pack(side="top")
        elif self.is_on_right_half():
            spacer.configure(width=self.ghost_control_space, height=1)
            spacer.pack(side="left")
            cards_frame.pack(side="left")
        else:
            cards_frame.pack(side="left")
            spacer.configure(width=self.ghost_control_space, height=1)
            spacer.pack(side="left")
        total = len(self.ghost_accounts)
        card_width = 47 if total <= self.MAX_COMFORTABLE_CELLS else max(38, 658 // total)
        for account in self.ghost_accounts:
            card = ctk.CTkButton(
                cards_frame, text="", image=self.image_for(account.get("classe", "Inconnu")),
                width=card_width, height=46, corner_radius=10,
                fg_color=panel_alt, hover_color=theme.get("accent", "#2f80c3"),
                border_width=1, border_color=panel_alt,
                command=lambda selected=account: self.select_ghost_character(selected),
            )
            card.pack(side="top" if is_vertical else "left", padx=2, pady=2)
        self.fit_window_to_content(self.ghost_window, self.ghost_outer)
        self.sync_ghost_bar()

    def select_ghost_team(self, _event=None):
        """A click on the ghost surface is a simple Team 1/Team 2 swap."""
        if self.begin_ghost_switch() and self.ghost_team:
            self.debug(f"clic fantôme: changement vers {self.ghost_team}")
            self.on_team_selected(self.ghost_team)

    def select_ghost_character(self, account):
        """A ghost portrait swaps the team, then focuses that exact account."""
        if not self.ghost_team or not self.begin_ghost_switch():
            return
        self.debug(f"clic portrait fantôme: {account.get('name', '')} vers {self.ghost_team}")
        self.on_team_selected(self.ghost_team)
        self.parent_root.after(35, lambda selected=account: self.on_character_selected(selected))

    def begin_ghost_switch(self):
        """Accept exactly one action for a physical mouse press.

        Rebuilding an overlapped borderless window while Windows still routes
        the original press can dispatch it again to the newly created ghost.
        Keep the action locked until the button has truly been released.
        """
        if self._ghost_switch_locked:
            self.debug("clic fantôme ignoré: verrou actif")
            return False
        self._ghost_switch_locked = True
        self.ghost_window.withdraw()
        self.parent_root.after(80, self.release_ghost_switch_after_mouse_up)
        return True

    def release_ghost_switch_after_mouse_up(self):
        try:
            mouse_is_down = ctypes.windll.user32.GetAsyncKeyState(0x01) < 0
        except Exception:
            mouse_is_down = False
        if mouse_is_down:
            self.parent_root.after(80, self.release_ghost_switch_after_mouse_up)
            return
        self._ghost_switch_locked = False
        self.debug("verrou clic fantôme libéré")

    def fit_window_to_content(self, window, content):
        """Remove unused popup surface left by a previous larger layout."""
        content.update_idletasks()
        width = max(1, content.winfo_reqwidth() + 2)
        height = max(1, content.winfo_reqheight() + 2)
        self._shape_sizes[window.winfo_id()] = (width, height)
        window.geometry(f"{width}x{height}+{window.winfo_x()}+{window.winfo_y()}")
        window.update_idletasks()
        self.debug(f"taille cible={width}x{height} fenêtre={window.winfo_id()} contenu={content.winfo_width()}x{content.winfo_height()}")

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
        self.apply_rounded_shape(self.ghost_window)
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.keep_ghost_below_main()
        self.parent_root.after(10, self.keep_ghost_below_main)

    def keep_ghost_below_main(self):
        """Keep the translucent companion directly below the main module."""
        try:
            main_widget = self.window.winfo_id()
            ghost_widget = self.ghost_window.winfo_id()
            main_root = ctypes.windll.user32.GetAncestor(main_widget, 2) or main_widget
            ghost_root = ctypes.windll.user32.GetAncestor(ghost_widget, 2) or ghost_widget
            flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
            # Reassert both in the topmost band, always placing the opaque
            # main popup last.  This is more reliable than relative stacking
            # across the two Tk native root HWNDs.
            ctypes.windll.user32.SetWindowPos(ghost_root, -1, 0, 0, 0, 0, flags)
            ctypes.windll.user32.SetWindowPos(main_root, -1, 0, 0, 0, 0, flags)
            self.debug(f"z-order: fantôme={ghost_root} < principal={main_root}")
        except Exception:
            pass

    def make_ghost_non_activating(self):
        """Let the ghost receive clicks without Windows raising it on top."""
        try:
            ghost_widget = self.ghost_window.winfo_id()
            ghost_root = ctypes.windll.user32.GetAncestor(ghost_widget, 2) or ghost_widget
            ex_style = ctypes.windll.user32.GetWindowLongW(ghost_root, -20)  # GWL_EXSTYLE
            ctypes.windll.user32.SetWindowLongW(ghost_root, -20, ex_style | 0x08000000)  # WS_EX_NOACTIVATE
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | NOACTIVATE | FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(ghost_root, 0, 0, 0, 0, 0, flags)
            self.debug(f"fantôme non-activable hwnd={ghost_root}")
            self.keep_ghost_below_main()
        except Exception:
            pass

    def apply_rounded_shape(self, window):
        """Clip a borderless Windows popup to its rounded module outline.

        `-transparentcolor` conflicts with the alpha compositing used by the
        ghost bar on some Windows builds, briefly exposing a black rectangle.
        A native region has no such repaint artefact.
        """
        try:
            window.update_idletasks()
            width, height = self._shape_sizes.get(
                window.winfo_id(), (window.winfo_width(), window.winfo_height())
            )
            if width < 2 or height < 2:
                return
            widget_hwnd = window.winfo_id()
            # CustomTkinter can expose a child HWND here.  The black rectangle
            # belongs to the native root window, so clip that actual surface.
            root_hwnd = ctypes.windll.user32.GetAncestor(widget_hwnd, 2) or widget_hwnd
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, 28, 28)
            result = ctypes.windll.user32.SetWindowRgn(root_hwnd, region, True)
            self.debug(f"forme widget={widget_hwnd} racine={root_hwnd} cible={width}x{height} actuelle={window.winfo_width()}x{window.winfo_height()} résultat={result}")
        except Exception:
            pass

    def update_card_states(self):
        try:
            foreground = win32gui.GetForegroundWindow()
        except Exception:
            foreground = 0
        if foreground != self._last_observed_foreground:
            self._last_observed_foreground = foreground
            self.debug(f"focus observé hwnd={foreground}")
        tracked_windows = {account.get("hwnd") for _, account in self.cards}
        # Interacting with DOSOFT itself must not repaint the overlaid bars.
        if foreground not in tracked_windows:
            return
        if foreground == self._last_foreground:
            return
        self._last_foreground = foreground
        self._pending_foreground = foreground
        self.debug(f"focus jeu hwnd={foreground}; visible={self.window.winfo_viewable()}")
        previous = self._selected_hwnd
        self._selected_hwnd = foreground
        if self.window.winfo_viewable():
            self.animate_card_selection(previous, foreground)
        else:
            self.apply_card_states(foreground)

    @staticmethod
    def blend_color(start, end, amount):
        """Mix two #RRGGBB colours for a lightweight selection fade."""
        start = start.lstrip("#")
        end = end.lstrip("#")
        try:
            values = [
                round(int(start[i:i + 2], 16) + (int(end[i:i + 2], 16) - int(start[i:i + 2], 16)) * amount)
                for i in (0, 2, 4)
            ]
            return "#" + "".join(f"{value:02x}" for value in values)
        except ValueError:
            return end if amount >= 0.5 else start

    def animate_card_selection(self, previous_hwnd, selected_hwnd):
        """Fade only portrait colours; the bars themselves never blink."""
        self._color_transition_token += 1
        token = self._color_transition_token
        self.debug(f"couleur: transition {previous_hwnd} -> {selected_hwnd}")
        for step in range(5):
            self.parent_root.after(
                step * 28,
                lambda progress=step / 4, current=token: self.apply_card_transition(
                    previous_hwnd, selected_hwnd, progress, current
                ),
            )

    def apply_card_transition(self, previous_hwnd, selected_hwnd, progress, token):
        if token != self._color_transition_token:
            return
        theme = self.theme
        panel_alt = theme.get("panel_alt", "#34495e")
        accent = theme.get("accent", "#2f80c3")
        border = theme.get("border", "#78b9e8")
        leader_name = self.config.data.get("leader_name", "")
        gold = "#e5bd5d"
        for button, account in self.cards:
            hwnd = account.get("hwnd")
            if hwnd == selected_hwnd:
                color = self.blend_color(panel_alt, accent, progress)
                outline = self.blend_color(panel_alt, border, progress)
            elif hwnd == previous_hwnd:
                color = self.blend_color(accent, panel_alt, progress)
                outline = self.blend_color(border, panel_alt, progress)
            else:
                color = panel_alt
                outline = panel_alt
            is_leader = account.get("name") == leader_name
            button.configure(
                fg_color=color,
                border_color=gold if is_leader else outline,
                border_width=2 if is_leader or hwnd in (previous_hwnd, selected_hwnd) else 1,
            )

    def apply_card_states(self, foreground):
        """Paint card state only once per actual foreground-window change."""
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

    def soft_refresh_cards(self):
        """Briefly hide both layered popups while Windows changes focus.

        This prevents the compositor from showing an intermediate black layer
        when CustomTkinter repaints two overlapping borderless windows.
        """
        self._transitioning = True
        self.debug("transition: masquage")
        self.ghost_window.withdraw()
        self.window.withdraw()
        self.parent_root.after(70, self.finish_soft_refresh)

    def finish_soft_refresh(self):
        try:
            self.apply_card_states(self._pending_foreground)
            if self.config.data.get("character_bar_visible", False):
                self.window.deiconify()
                self.apply_rounded_shape(self.window)
                self.window.lift()
                self.sync_ghost_bar()
            self.debug("transition: affichage")
        finally:
            self._transitioning = False

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
