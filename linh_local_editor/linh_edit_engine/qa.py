from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class QAResult:
    passed: bool
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    decoded_ok: bool
    errors: tuple[str, ...]


def _tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"{name} not found")
    return resolved


def _fraction(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" not in value:
        return float(value)
    n, d = value.split("/", 1)
    return float(n) / float(d) if float(d) else 0.0


def verify_output(
    output: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> QAResult:
    output = output.expanduser().resolve()
    probe = subprocess.run(
        [
            _tool("ffprobe"),
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if probe.returncode != 0:
        return QAResult(False, 0, 0, 0, 0, "", None, False, (probe.stderr.strip(),))

    payload = json.loads(probe.stdout)
    streams = payload.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    actual_fps = _fraction(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    errors: list[str] = []
    if video.get("codec_name") != "h264":
        errors.append("video codec is not h264")
    if int(video.get("width") or 0) != width or int(video.get("height") or 0) != height:
        errors.append("unexpected output dimensions")
    if abs(actual_fps - fps) > 0.05:
        errors.append("unexpected output fps")
    if audio is not None and audio.get("codec_name") != "aac":
        errors.append("audio codec is not aac")

    decode = subprocess.run(
        [_tool("ffmpeg"), "-v", "error", "-i", str(output), "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    decoded_ok = decode.returncode == 0
    if not decoded_ok:
        errors.append("full decode failed")

    return QAResult(
        passed=not errors,
        duration=float(payload.get("format", {}).get("duration") or 0),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=actual_fps,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        decoded_ok=decoded_ok,
        errors=tuple(errors),
    )
