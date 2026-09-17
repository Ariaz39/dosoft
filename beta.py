"""Launch the local DOSOFT beta with isolated user settings."""

from pathlib import Path
import os


beta_data_dir = Path(__file__).resolve().parent / ".beta-data"
beta_data_dir.mkdir(exist_ok=True)
os.environ["DOSOFT_SETTINGS_FILE"] = str(beta_data_dir / "settings.json")
os.environ["DOSOFT_WAKFU_DEBUG_LOG"] = str(beta_data_dir / "wakfu-autofocus-debug.log")

from main import start_application


if __name__ == "__main__":
    start_application()
