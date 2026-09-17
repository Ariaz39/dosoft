"""Launch the local DOSOFT beta with isolated user settings."""

from pathlib import Path
import os


beta_data_dir = Path(__file__).resolve().parent / ".beta-data"
beta_data_dir.mkdir(exist_ok=True)
os.chdir(beta_data_dir)

from main import start_application


if __name__ == "__main__":
    start_application()
