from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .cache import (
    CACHE_SCHEMA,
    cache_matches,
    read_json,
    source_cache_dir,
    source_signature,
    write_json_atomic,
)
from .media import MediaInfo, probe
from .tools import resolve_tool


@dataclass(frozen=True, slots=True)
class ProxyResult:
    source: str
    proxy: str
    reused: bool
    width: int
    height: int
    fps: float


def _proxy_dimensions(info: MediaInfo) -> tuple[int, int]:
    if info.height >= info.width:
        return 720, 1280
    return 1280, 720


def ensure_proxy(
    source: Path,
    *,
    force: bool = False,
    max_fps: int = 30,
) -> ProxyResult:
    source = source.expanduser().resolve()
    info = probe(source)
    cache_dir = source_cache_dir(source)
    manifest = cache_dir / "proxy.json"
    target = cache_dir / "analysis_proxy.mp4"

    payload = read_json(manifest)
    if (
        not force
        and target.is_file()
        and cache_matches(payload, source)
        and int(payload.get("proxy_version", 0)) == 1
    ):
        try:
            manifest.touch()
        except OSError:
            pass
        return ProxyResult(
            source=str(source),
            proxy=str(target),
            reused=True,
            width=int(payload.get("width", 0)),
            height=int(payload.get("height", 0)),
            fps=float(payload.get("fps", 0.0)),
        )

    width, height = _proxy_dimensions(info)
    fps = min(float(max_fps), info.fps or float(max_fps))
    temp = target.with_suffix(".partial.mp4")
    command = [
        resolve_tool("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={fps:.6f}"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(temp),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        check=False,
    )
    if completed.returncode != 0 or not temp.is_file():
        raise RuntimeError(
            (completed.stderr or f"Không tạo được proxy: {source.name}")[-3000:]
        )
    temp.replace(target)

    signature = source_signature(source)
    source_info = asdict(info)
    source_info["path"] = str(info.path)
    payload = {
        "schema": CACHE_SCHEMA,
        "kind": "proxy",
        "proxy_version": 1,
        "source_signature": asdict(signature),
        "source_info": source_info,
        "proxy": str(target),
        "width": width,
        "height": height,
        "fps": round(fps, 6),
    }
    write_json_atomic(manifest, payload)
    return ProxyResult(
        source=str(source),
        proxy=str(target),
        reused=False,
        width=width,
        height=height,
        fps=fps,
    )
