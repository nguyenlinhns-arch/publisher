from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "MXHVideoEditor"
OUTPUT_FOLDER_NAME = "MXH Video Editor"


def _app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    target = base / APP_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = Path(tempfile.gettempdir()) / APP_NAME
        target.mkdir(parents=True, exist_ok=True)
    return target


def _default_output_dir(root_dir: Path) -> Path:
    videos = Path.home() / "Videos"
    try:
        videos.mkdir(parents=True, exist_ok=True)
        target = videos / OUTPUT_FOLDER_NAME
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        target = root_dir / "outputs"
        target.mkdir(parents=True, exist_ok=True)
        return target


@dataclass(frozen=True, slots=True)
class EditorConfig:
    root_dir: Path
    output_dir: Path
    cache_dir: Path

    def ensure_directories(self) -> None:
        for directory in (self.root_dir, self.output_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)


def load_config(output_dir: Path | None = None) -> EditorConfig:
    root = _app_data_dir()
    config = EditorConfig(
        root_dir=root,
        output_dir=(output_dir.expanduser().resolve() if output_dir else _default_output_dir(root)),
        cache_dir=root / "cache",
    )
    config.ensure_directories()
    return config

