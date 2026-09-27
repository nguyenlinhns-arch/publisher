from __future__ import annotations

import math
import subprocess
from pathlib import Path

from .media import probe_duration
from .tools import resolve_tool


def extract_contact_sheet(
    video: Path,
    target: Path,
    *,
    tiles: int = 12,
    columns: int = 4,
    tile_width: int = 270,
    tile_height: int = 480,
) -> Path:
    video = video.expanduser().resolve()
    target = target.expanduser().resolve()
    if not video.is_file():
        raise RuntimeError(f"Không tìm thấy video preview: {video}")
    if tiles < 1 or columns < 1:
        raise ValueError("tiles/columns phải lớn hơn 0.")

    duration = max(0.2, probe_duration(video))
    rows = max(1, math.ceil(tiles / columns))
    fps = max(0.01, tiles / duration)
    target.parent.mkdir(parents=True, exist_ok=True)

    filter_graph = (
        f"fps={fps:.8f},"
        f"scale={tile_width}:{tile_height}:force_original_aspect_ratio=decrease,"
        f"pad={tile_width}:{tile_height}:(ow-iw)/2:(oh-ih)/2,"
        f"tile={columns}x{rows}:padding=8:margin=8"
    )
    completed = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            filter_graph,
            "-frames:v",
            "1",
            str(target),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        raise RuntimeError((completed.stderr or "Không tạo được contact sheet.")[-2000:])
    return target
