from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .tools import resolve_tool


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str
    audio_codec: str | None


def _tool(name: str) -> str:
    return resolve_tool(name)


def _fraction(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" not in value:
        return float(value)
    n, d = value.split("/", 1)
    return float(n) / float(d) if float(d) else 0.0


def probe(path: Path) -> MediaInfo:
    path = path.expanduser().resolve()
    completed = subprocess.run(
        [
            _tool("ffprobe"),
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"Không đọc được {path.name}")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    video = next((x for x in streams if x.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError(f"{path.name} không có video stream.")
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    return MediaInfo(
        path=path,
        duration=float(payload.get("format", {}).get("duration") or video.get("duration") or 0),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        has_audio=audio is not None,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name") or "") if audio else None,
    )


def infer_role(path: Path) -> str:
    value = path.stem.casefold()
    rules = [
        (r"thác|núi|cao nguyên|landscape|toàn cảnh", "place"),
        (r"cầu|sông|đèo|đường|road|xe|di chuyển", "road_reset"),
        (r"xã|làng|buôn|nhà|địa bàn", "life"),
        (r"người|linh|gặp|làm việc|họp|công tác", "human"),
        (r"detail|chi tiết|bếp|món|cà phê|coffee", "detail"),
    ]
    for pattern, role in rules:
        if re.search(pattern, value):
            return role
    return "detail"


def default_segment_duration(role: str, available: float) -> float:
    target = {
        "work": 2.5,
        "admin": 2.5,
        "road_reset": 3.0,
        "detail": 3.4,
        "place": 3.8,
        "life": 3.8,
        "human": 4.8,
        "emotion": 4.8,
        "ending": 5.5,
        "visual_hook": 3.2,
    }.get(role, 3.4)
    return max(1.0, min(target, available))


def probe_duration(path: Path) -> float:
    path = path.expanduser().resolve()
    completed = subprocess.run(
        [
            _tool("ffprobe"),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"Không đọc được thời lượng {path.name}.")
    payload = json.loads(completed.stdout)
    duration = float(payload.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise RuntimeError(f"Thời lượng không hợp lệ: {path.name}")
    return duration
