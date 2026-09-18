"""Launch the local DOSOFT beta with isolated user settings."""

from pathlib import Path
import os
import traceback


beta_data_dir = Path(__file__).resolve().parent / ".beta-data"
beta_data_dir.mkdir(exist_ok=True)
os.environ["DOSOFT_SETTINGS_FILE"] = str(beta_data_dir / "settings.json")
os.environ["DOSOFT_WAKFU_DEBUG_LOG"] = str(beta_data_dir / "wakfu-autofocus-debug.log")
os.environ["DOSOFT_QUICKBAR_DEBUG_LOG"] = str(beta_data_dir / "quickbar-debug.log")
(beta_data_dir / "quickbar-debug.log").write_text("", encoding="utf-8")
os.environ["DOSOFT_APP_TITLE"] = "BETA DOSOFT 1.3.1"

# Le venv Python 3.13 utilisé pour la bêta ne transporte pas Tcl/Tk ; on
# rattache explicitement le runtime local afin que CustomTkinter puisse créer
# sa fenêtre, y compris après une relance élevée.
tcl_root = Path(__file__).resolve().parent.parent / "python313-tcl"
os.environ["TCL_LIBRARY"] = str(tcl_root / "tcl8.6")
os.environ["TK_LIBRARY"] = str(tcl_root / "tk8.6")

from main import start_application


if __name__ == "__main__":
    try:
        start_application()
    except Exception:
        (beta_data_dir / "startup-error.log").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        raise
