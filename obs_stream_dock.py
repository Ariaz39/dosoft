"""Optional borderless OBS controls, created only while the extension is enabled."""

import ctypes
import queue
from ctypes import wintypes

import customtkinter as ctk
import win32api
from PIL import Image

from resource_paths import resource_path
from obs_icon_catalog import DEFAULT_OBS_ICON, obs_icon_path
from streamdeck_model import is_stateful_streamdeck_command, ordered_streamdeck_controls


class ObsStreamDock(ctk.CTkToplevel):
    def __init__(self, root, bridge):
        super().__init__(root)
        self.bridge = bridge
        self._drag_origin = None
        self.states = dict(bridge.profile.data.get("dock_states", {}))
        self.buttons = {}
        self.control_commands = {}
        self.control_definitions = {}
        self._control_responses = queue.Queue()
        self._last_fitted_geometry = None
        self._rebuild_generation = 0
        self.scale = self._profile_scale()
        self.images = self._load_images()
        self.custom_images = {}
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.outer = ctk.CTkFrame(
            self, corner_radius=round(14 * self.scale), border_width=1,
            fg_color="#20213d", border_color="#b9e936",
        )
        self.outer.pack(padx=1, pady=1)
        self.content = ctk.CTkFrame(self.outer, fg_color="transparent")
        padding = max(3, round(5 * self.scale))
        self.content.pack(padx=padding, pady=padding)
        self.rebuild_buttons()
        for widget in (self, self.outer, self.content):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.drag)
            widget.bind("<ButtonRelease-1>", self.finish_drag)
        self.after_idle(self.fit_and_position_window)
        self.after_idle(self.make_native_independent)
        self.after(80, self.apply_rounded_shape)
        self.after(100, self._poll_control_responses)
        self.after(3000, self._periodic_state_refresh)

    @staticmethod
    def clamp_to_work_areas(position, size, work_areas, margin=8):
        """Keep the complete dock inside one real monitor work area.

        The virtual desktop rectangle may contain gaps between monitors and
        includes taskbars. A position can therefore be valid for the virtual
        desktop while remaining invisible to the user.
        """
        width, height = size
        left, top = int(position[0]), int(position[1])
        if not work_areas:
            return left, top

        center_x = left + width // 2
        center_y = top + height // 2
        target = next(
            (
                area for area in work_areas
                if area[0] <= center_x < area[2] and area[1] <= center_y < area[3]
            ),
            None,
        )
        if target is None:
            def distance(area):
                nearest_x = min(max(center_x, area[0]), area[2])
                nearest_y = min(max(center_y, area[1]), area[3])
                return (center_x - nearest_x) ** 2 + (center_y - nearest_y) ** 2
            target = min(work_areas, key=distance)

        work_left, work_top, work_right, work_bottom = target
        safe_left = work_left + margin
        safe_top = work_top + margin
        safe_right = max(safe_left, work_right - width - margin)
        safe_bottom = max(safe_top, work_bottom - height - margin)
        return (
            max(safe_left, min(left, safe_right)),
            max(safe_top, min(top, safe_bottom)),
        )

    @staticmethod
    def monitor_work_areas():
        try:
            return [
                tuple(win32api.GetMonitorInfo(monitor)["Work"])
                for monitor, _device, _rect in win32api.EnumDisplayMonitors()
            ]
        except Exception:
            return []

    def _profile_scale(self):
        try:
            return max(0.6, min(1.6, float(self.bridge.profile.data.get("streamdeck_scale", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def _load_images(self):
        try:
            image = Image.open(resource_path("resources", "skin", "stream dock", "stream-controls.png"))
            width, height = image.size
            icon_size = max(18, round(30 * self.scale))
            return [ctk.CTkImage(
                light_image=image.crop((i * width // 3, 0, (i + 1) * width // 3, height)),
                dark_image=image.crop((i * width // 3, 0, (i + 1) * width // 3, height)),
                size=(icon_size, icon_size),
            ) for i in range(3)]
        except Exception:
            return [None, None, None]

    def controls(self):
        profile = self.bridge.profile.data
        controls = []
        builtin_images = {
            "microphone": self.images[0], "camera": self.images[1], "pause": self.images[2],
        }
        for index, item in enumerate(ordered_streamdeck_controls(profile)):
            icon_id = str(item.get("icon_id") or DEFAULT_OBS_ICON)
            image = builtin_images.get(str(item.get("id")))
            if image is None and icon_id not in self.custom_images:
                try:
                    source_image = Image.open(obs_icon_path(icon_id))
                    icon_size = max(18, round(30 * self.scale))
                    self.custom_images[icon_id] = ctk.CTkImage(
                        source_image, source_image, size=(icon_size, icon_size)
                    )
                except Exception:
                    self.custom_images[icon_id] = None
            if image is None:
                image = self.custom_images.get(icon_id)
            controls.append({
                "id": str(item.get("id") or f"custom-{index}"),
                "label": str(item.get("label") or "OBS")[:8],
                "command": str(item.get("command")),
                "source": str(item.get("source", "")),
                "scene": str(item.get("scene", "")),
                "image": image,
            })
        return controls

    def rebuild_buttons(self):
        self._rebuild_generation += 1
        generation = self._rebuild_generation
        for widget in self.content.winfo_children():
            widget.destroy()
        self.buttons.clear()
        self.control_commands.clear()
        self.control_definitions.clear()
        self.scale = self._profile_scale()
        self.images = self._load_images()
        self.custom_images.clear()
        padding = max(3, round(5 * self.scale))
        gap = max(1, round(3 * self.scale))
        button_size = max(30, round(48 * self.scale))
        self.outer.configure(corner_radius=max(8, round(14 * self.scale)))
        self.content.pack_configure(padx=padding, pady=padding)
        layout = self.bridge.profile.data.get("streamdeck_layout", "horizontal")
        columns = 2 if layout == "grid_2" else 3 if layout == "grid_3" else 0
        for index, control in enumerate(self.controls()):
            button = ctk.CTkButton(
                self.content, text="" if control["image"] else control["label"], image=control["image"],
                width=button_size, height=button_size, fg_color="#35375c", hover_color="#9ebd05",
                command=lambda value=control: self._control(value),
            )
            if layout == "vertical":
                button.pack(side="top", padx=gap, pady=gap)
            elif columns:
                button.grid(row=index // columns, column=index % columns, padx=gap, pady=gap)
            else:
                button.pack(side="left", padx=gap)
            self.buttons[control["id"]] = button
            self.control_commands[control["id"]] = control["command"]
            self.control_definitions[control["id"]] = control
            if not is_stateful_streamdeck_command(control["command"]):
                self.states.pop(control["id"], None)
            self.apply_state(control["id"])
        # Let Tk calculate the complete requested size once. A generation token
        # prevents callbacks from earlier rapid edits from fitting an obsolete
        # layout after the newest one has already been displayed.
        self.after(40, lambda current=generation: self.finish_rebuild(current))
        self.after(150, self._refresh_control_states)

    def finish_rebuild(self, generation):
        if generation != self._rebuild_generation:
            return
        self.fit_and_position_window()
        if self.bridge.profile.data.get("dock_enabled", False):
            self.show_and_recover(fit=False)

    def position_window(self):
        position = self.bridge.profile.data.get("dock_position", [20, 100])
        self.geometry(f"+{int(position[0])}+{int(position[1])}")

    def fit_and_position_window(self):
        """Fit the borderless dock once on every Windows DPI scale.

        Widget requested sizes are physical pixels while CTk's geometry API
        expects unscaled dimensions. Reverse the CTk window scale before
        sizing, and keep an old saved position inside the virtual desktop.
        """
        try:
            self.update_idletasks()
            width = max(1, self.outer.winfo_reqwidth() + 2)
            height = max(1, self.outer.winfo_reqheight() + 2)
            reverse_scale = getattr(self, "_reverse_window_scaling", lambda value: value)
            logical_width = max(1, reverse_scale(width))
            logical_height = max(1, reverse_scale(height))

            position = self.bridge.profile.data.get("dock_position", [20, 100])
            work_areas = self.monitor_work_areas()
            if not work_areas:
                work_areas = [(0, 0, self.winfo_screenwidth(), self.winfo_screenheight())]
            left, top = self.clamp_to_work_areas(position, (width, height), work_areas)
            if [left, top] != list(position):
                self.bridge.profile.data["dock_position"] = [left, top]
                self.bridge.profile.save()
                self.bridge._record(
                    f"DOCK : position hors écran corrigée vers {left},{top}"
                )
            self.geometry(f"{logical_width}x{logical_height}+{left}+{top}")
            self.update_idletasks()
            if abs(self.winfo_width() - width) > 1 or abs(self.winfo_height() - height) > 1:
                self.tk.call("wm", "geometry", self._w, f"{width}x{height}+{left}+{top}")
                self.update_idletasks()
            actual_geometry = (
                self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y()
            )
            if actual_geometry != self._last_fitted_geometry:
                self._last_fitted_geometry = actual_geometry
                self.bridge._record(
                    "DOCK : géométrie adaptée "
                    f"cible={width}x{height} réelle={actual_geometry[0]}x{actual_geometry[1]} "
                    f"position={actual_geometry[2]},{actual_geometry[3]}"
                )
            self.apply_rounded_shape()
        except Exception:
            self.position_window()

    def show_and_recover(self, fit=True):
        """Show the dock and reassert its native topmost state."""
        try:
            self.deiconify()
            if fit:
                self.fit_and_position_window()
            self.attributes("-topmost", True)
            self.lift()
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
            self.make_native_independent(hwnd)
            flags = 0x0001 | 0x0002 | 0x0010 | 0x0040  # NOSIZE|NOMOVE|NOACTIVATE|SHOWWINDOW
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            self.bridge._record(
                "DOCK : visibilité restaurée "
                f"hwnd={hwnd} rect={rect.left},{rect.top},{rect.right},{rect.bottom}"
            )
        except Exception as error:
            self.bridge._record(f"DOCK : restauration impossible : {error}")

    def make_native_independent(self, hwnd=None):
        """Detach the dock from Tk's hidden root on Windows.

        The Stream Deck must remain visible when F12 hides the main DoSoft UI.
        An owned native popup is automatically hidden with its owner, whatever
        Tk's own Toplevel state says.
        """
        try:
            self.update_idletasks()
            hwnd = hwnd or (
                ctypes.windll.user32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
            )
            setter = ctypes.windll.user32.SetWindowLongPtrW
            setter.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
            setter.restype = ctypes.c_void_p
            setter(hwnd, -8, ctypes.c_void_p(0))  # GWLP_HWNDPARENT: no owner
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
        except Exception as error:
            self.bridge._record(f"DOCK : détachement natif impossible : {error}")

    def is_natively_visible(self):
        """Read the real HWND state even while the Tk root is withdrawn.

        ``winfo_viewable`` reports false for a Toplevel whose master is hidden,
        even when ``SetWindowPos(SHOWWINDOW)`` keeps the independent dock on
        screen. Using it in the watchdog recreated a native window every three
        seconds and made Windows display its busy cursor continuously.
        """
        try:
            hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return False
            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False
            return rect.right > rect.left and rect.bottom > rect.top
        except Exception:
            return False

    def start_drag(self, event):
        self._drag_origin = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())

    def drag(self, event):
        if self._drag_origin:
            x0, y0, left, top = self._drag_origin
            self.geometry(f"+{left + event.x_root - x0}+{top + event.y_root - y0}")

    def finish_drag(self, _event):
        if self._drag_origin:
            self.bridge.profile.data["dock_position"] = [self.winfo_x(), self.winfo_y()]
            self.bridge.profile.save()
        self._drag_origin = None

    def apply_rounded_shape(self):
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
            rect = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = max(1, rect.right - rect.left)
                height = max(1, rect.bottom - rect.top)
            else:
                width, height = self.winfo_width(), self.winfo_height()
            scale = getattr(self, "_get_window_scaling", lambda: 1.0)()
            radius = max(16, round(28 * scale))
            region = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, width + 1, height + 1, radius, radius,
            )
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
        except Exception:
            pass

    def apply_state(self, control_id):
        button = self.buttons.get(control_id)
        if not button:
            return
        is_off = bool(self.states.get(control_id, False))
        button.configure(
            fg_color="#a3434d" if is_off else "#35375c",
            hover_color="#c95862" if is_off else "#9ebd05",
        )

    def _control(self, control):
        control_id = control["id"]

        def completed(response):
            self._control_responses.put((control_id, response))

        self.bridge.control_custom(
            control["command"], control.get("source", ""), control.get("scene", ""), completed
        )

    def _refresh_control_states(self):
        try:
            if not self.winfo_viewable():
                return
        except Exception:
            return
        for control_id, control in tuple(self.control_definitions.items()):
            if not is_stateful_streamdeck_command(control.get("command")):
                continue

            def completed(response, value=control_id):
                self._control_responses.put((value, response, False))

            self.bridge.query_control_state(
                control["command"], control.get("source", ""),
                control.get("scene", ""), completed,
            )

    def _periodic_state_refresh(self):
        # Never manipulate a native window from this timer. Tk reports an
        # override-redirect popup as non-viewable in several perfectly valid
        # states; attempting to "repair" it periodically recreated HWNDs and
        # caused Windows' spinning busy cursor during gameplay. Visibility is
        # restored only at startup or after an explicit profile reload.
        self._refresh_control_states()
        try:
            self.after(3000, self._periodic_state_refresh)
        except Exception:
            pass

    def _poll_control_responses(self):
        try:
            while True:
                item = self._control_responses.get_nowait()
                if len(item) == 2:
                    control_id, response = item
                    allow_toggle = True
                else:
                    control_id, response, allow_toggle = item
                self._apply_control_response(control_id, response, allow_toggle)
        except queue.Empty:
            pass
        try:
            self.after(100, self._poll_control_responses)
        except Exception:
            pass

    def _apply_control_response(self, control_id, response, allow_toggle=True):
        if not response.get("ok"):
            return
        command = self.control_commands.get(control_id, "")
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        response_stateful = data.get("stateful")
        if not is_stateful_streamdeck_command(command) or response_stateful is False:
            # A direct scene alias is an impulse action: it must never look
            # latched or require a second click to clear its colour.
            if control_id in self.states:
                self.states.pop(control_id, None)
                self.bridge.profile.data["dock_states"] = self.states
                if allow_toggle:
                    self.bridge.profile.save()
            self.apply_state(control_id)
            return
        actual_off = data.get("off")
        if isinstance(actual_off, bool):
            self.states[control_id] = actual_off
        elif allow_toggle:
            # Compatibility with plugin 0.3.0 and older: their successful
            # response did not include the resulting OBS state.
            self.states[control_id] = not bool(self.states.get(control_id, False))
        else:
            return
        self.bridge.profile.data["dock_states"] = self.states
        if allow_toggle:
            self.bridge.profile.save()
        self.apply_state(control_id)
