from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def extract_cover(video: Path, target: Path, *, at_seconds: float = 1.5) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Không tìm thấy ffmpeg.")
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-ss", f"{max(0.0, at_seconds):.3f}",
            "-i", str(video),
            "-frames:v", "1",
            "-q:v", "2",
            str(target),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Không tạo được ảnh bìa.")
    return target
