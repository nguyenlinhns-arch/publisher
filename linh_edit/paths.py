from __future__ import annotations

import os
import tempfile
from pathlib import Path


def app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    target = root / "LinhEdit"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = Path(tempfile.gettempdir()) / "LinhEdit"
        target.mkdir(parents=True, exist_ok=True)
    return target


def output_dir() -> Path:
    target = Path.home() / "Videos" / "Linh Edit"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = app_data_dir() / "outputs"
        target.mkdir(parents=True, exist_ok=True)
    return target
