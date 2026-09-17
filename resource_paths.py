"""Centralised paths for assets bundled with DOSOFT."""

from __future__ import annotations

import os
import sys


def resource_path(*parts: str) -> str:
    """Return an asset path both from source and from a PyInstaller build."""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


def skin_path(class_name: str, *, wheel: bool = False) -> str:
    """Prefer beta resource skins while retaining legacy skins as a fallback."""
    filename = class_name.lower()
    if wheel:
        filename = f"{filename}_wheel"

    resource_skin = resource_path("resources", "skin", f"{filename}.png")
    if os.path.exists(resource_skin):
        return resource_skin

    return resource_path("skin", f"{class_name.lower()}.png")
