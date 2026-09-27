from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .tools import resolve_tool

PADDING = 8
MARGIN = 8


def extract_frame(
    source: Path,
    timestamp: float,
    target: Path,
    *,
    width: int = 270,
    height: int = 480,
) -> Path:
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".partial.jpg")

    completed = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.0, float(timestamp)):.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            ),
            "-q:v",
            "3",
            str(temp),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if completed.returncode != 0 or not temp.is_file():
        raise RuntimeError(
            (completed.stderr or f"Không lấy được frame tại {timestamp:.2f}s")[-2000:]
        )
    temp.replace(target)
    return target


def extract_candidate_frames(
    source: Path,
    timestamps: list[float],
    output_dir: Path,
    *,
    width: int = 270,
    height: int = 480,
) -> tuple[Path, ...]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for index, timestamp in enumerate(timestamps, start=1):
        target = output_dir / f"candidate_{index:02d}.jpg"
        if not target.is_file():
            extract_frame(
                source,
                timestamp,
                target,
                width=width,
                height=height,
            )
        result.append(target.resolve())
    return tuple(result)


def compose_contact_sheet(
    frames: tuple[Path, ...],
    target: Path,
    *,
    columns: int = 4,
    tile_width: int = 270,
    tile_height: int = 480,
) -> Path:
    if not frames:
        raise ValueError("Không có frame để tạo contact sheet.")
    columns = max(1, int(columns))
    rows = math.ceil(len(frames) / columns)
    canvas_width = MARGIN * 2 + columns * tile_width + (columns - 1) * PADDING
    canvas_height = MARGIN * 2 + rows * tile_height + (rows - 1) * PADDING
    canvas = Image.new("RGB", (canvas_width, canvas_height), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)

    for index, path in enumerate(frames):
        row, column = divmod(index, columns)
        left = MARGIN + column * (tile_width + PADDING)
        top = MARGIN + row * (tile_height + PADDING)
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            if image.size != (tile_width, tile_height):
                image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
                padded = Image.new("RGB", (tile_width, tile_height), (0, 0, 0))
                x = (tile_width - image.width) // 2
                y = (tile_height - image.height) // 2
                padded.paste(image, (x, y))
                image = padded
            canvas.paste(image, (left, top))
        label = str(index + 1)
        draw.rectangle((left + 6, top + 6, left + 34, top + 32), fill=(0, 0, 0))
        draw.text((left + 12, top + 9), label, fill=(255, 255, 255))

    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".partial.jpg")
    canvas.save(temp, format="JPEG", quality=90, optimize=True)
    temp.replace(target)
    return target
