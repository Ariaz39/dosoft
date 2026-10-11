"""Create recoverable user-data snapshots when the installed app version changes."""

import json
import os
from datetime import datetime
from pathlib import Path
import shutil


def ensure_release_backup(app_version, app_data_dir, files, keep=6):
    """Snapshot existing profiles once per application version.

    The installer may replace binaries, but user data stays in AppData.  This
    extra snapshot makes schema migrations reversible without touching OBS'
    own scene collections.
    """
    app_data_dir = Path(app_data_dir)
    state_path = app_data_dir / "release-state.json"
    previous = ""
    try:
        previous = str(json.loads(state_path.read_text(encoding="utf-8")).get("version", ""))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass
    app_version = str(app_version)
    if previous == app_version:
        return None

    existing = [Path(path) for path in files if Path(path).is_file()]
    backup_dir = None
    if existing:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        label = f"{previous or 'pre-install'}-to-{app_version}"
        backup_dir = app_data_dir / "backups" / f"release-{label}-{stamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for source in existing:
            shutil.copy2(source, backup_dir / source.name)

    app_data_dir.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"version": app_version}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, state_path)

    backup_root = app_data_dir / "backups"
    if backup_root.exists():
        releases = sorted(
            (item for item in backup_root.iterdir() if item.is_dir() and item.name.startswith("release-")),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for obsolete in releases[max(1, int(keep)):]:
            shutil.rmtree(obsolete, ignore_errors=True)
    return backup_dir
