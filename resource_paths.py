"""Centralised paths for assets bundled with DOSOFT."""

from __future__ import annotations

import os
import sys


def resource_path(*parts: str) -> str:
    """Return an asset path both from source and from a PyInstaller build."""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


def skin_path(class_name: str, *, wheel: bool = False, engine: str | None = None) -> str:
    """Resolve a class visual for its engine, with legacy assets as fallback."""
    filename = class_name.removesuffix("_retro").lower()

    # Unity uses its original class art (``classe.png``); WAKFU uses the
    # dedicated head portraits (``classe tete.png``) copied as ``_tete``.
    if engine == "unity":
        unity_skin = resource_path("resources", "skin", "unity", f"{filename}.png")
        if os.path.exists(unity_skin):
            return unity_skin
    elif engine == "wakfu":
        wakfu_skin = resource_path("resources", "skin", "wakfu", f"{filename}_tete.png")
        if os.path.exists(wakfu_skin):
            return wakfu_skin

    if wheel:
        filename = f"{filename}_wheel"

    resource_skin = resource_path("resources", "skin", f"{filename}.png")
    if os.path.exists(resource_skin):
        return resource_skin

    return resource_path("skin", f"{class_name.lower()}.png")
