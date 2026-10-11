# -*- mode: python ; coding: utf-8 -*-
"""Reproducible one-file DOSOFT build used by build_release.ps1."""

import json
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


ROOT = Path(SPECPATH).resolve()

with (ROOT / "version.json").open("r", encoding="utf-8") as version_file:
    APP_VERSION = str(json.load(version_file)["version"])
VERSION_PARTS = tuple(int(part) for part in APP_VERSION.split(".")) + (0,)
VERSION_RESOURCE = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=VERSION_PARTS,
        prodvers=VERSION_PARTS,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                "040C04B0",
                [
                    StringStruct("CompanyName", "Dosoft"),
                    StringStruct("FileDescription", "DOSOFT BETA"),
                    StringStruct("FileVersion", APP_VERSION),
                    StringStruct("InternalName", "Dosoft_BETA"),
                    StringStruct("OriginalFilename", "Dosoft_BETA.exe"),
                    StringStruct("ProductName", "DOSOFT BETA"),
                    StringStruct("ProductVersion", APP_VERSION),
                ],
            )
        ]),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)


def collect_optional(package):
    """Collect a runtime package when installed without making the spec host-specific."""
    try:
        return collect_all(package)
    except Exception:
        return [], [], []


datas = [
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "skin"), "skin"),
    (str(ROOT / "sounds"), "sounds"),
    (str(ROOT / "logo.ico"), "."),
    (str(ROOT / "version.json"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
binaries = []
hiddenimports = [
    "customtkinter",
    "keyboard",
    "pygame",
    "pystray",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "winsdk.windows.ui.notifications",
    "winsdk.windows.ui.notifications.management",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.ui.notifications",
    "winrt.windows.ui.notifications.management",
]

for package in ("customtkinter", "winsdk", "winrt"):
    package_datas, package_binaries, package_hiddenimports = collect_optional(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[str(ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Dosoft_BETA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "logo.ico"),
    version=VERSION_RESOURCE,
    uac_admin=True,
)
