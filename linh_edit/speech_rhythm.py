from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .checkpoint import create_checkpoint
from .project import MediaItem, ProjectState
from .tools import resolve_tool

SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True, slots=True)
class SilenceSpan:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def parse_silencedetect(text: str) -> tuple[SilenceSpan, ...]:
    starts = [float(match.group(1)) for match in SILENCE_START_RE.finditer(text)]
    ends = [float(match.group(1)) for match in SILENCE_END_RE.finditer(text)]
    result: list[SilenceSpan] = []
    for start, end in zip(starts, ends):
        if end > start:
            result.append(SilenceSpan(round(start, 3), round(end, 3)))
    return tuple(result)


def detect_silences(
    audio: Path,
    *,
    noise_db: float = -35.0,
    minimum_seconds: float = 0.18,
) -> tuple[SilenceSpan, ...]:
    audio = audio.expanduser().resolve()
    if not audio.is_file():
        raise RuntimeError(f"Không tìm thấy audio để phân tích nhịp: {audio}")
    completed = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(audio),
            "-af",
            f"silencedetect=noise={noise_db:.1f}dB:d={minimum_seconds:.3f}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "silencedetect failed")[-3000:])
    return parse_silencedetect(completed.stderr)


def _punctuation_boundaries(transcript: str, duration: float) -> list[float]:
    parts = [
        item.strip()
        for item in re.split(r"(?<=[.!?…])\s+", transcript.strip())
        if item.strip()
    ]
    if len(parts) < 2:
        return []
    weights = [max(1, len(part.split())) for part in parts]
    total = sum(weights)
    cursor = 0.0
    boundaries: list[float] = []
    for weight in weights[:-1]:
        cursor += duration * weight / total
        boundaries.append(cursor)
    return boundaries


def _normalized_boundaries(
    project: ProjectState,
    *,
    silence_source: Path | None = None,
    minimum_segment: float = 1.2,
) -> list[float]:
    duration = sum(item.duration for item in project.timeline)
    if duration <= 0:
        return []

    silences: tuple[SilenceSpan, ...] = ()
    source = silence_source
    if source is None and project.voiceover:
        source = Path(project.voiceover)
    if source is not None:
        try:
            silences = detect_silences(source)
        except Exception:
            silences = ()

    boundaries = [
        (span.start + span.end) / 2
        for span in silences
        if span.end <= duration + 0.25
    ]
    if not boundaries and project.transcript.strip():
        boundaries = _punctuation_boundaries(project.transcript, duration)

    result: list[float] = []
    last = 0.0
    for value in sorted(boundaries):
        if value - last < minimum_segment:
            continue
        if duration - value < minimum_segment:
            continue
        result.append(value)
        last = value
    return result


def _split_timeline(
    timeline: list[MediaItem],
    boundaries: list[float],
    *,
    punch_scale: float = 1.035,
) -> list[MediaItem]:
    if not timeline:
        return []
    points = [0.0, *boundaries, sum(item.duration for item in timeline)]
    result: list[MediaItem] = []
    slot_cursor = 0.0
    segment_index = 0

    for item in timeline:
        slot_start = slot_cursor
        slot_end = slot_cursor + item.duration
        local_points = [slot_start]
        local_points.extend(
            point for point in points[1:-1]
            if slot_start < point < slot_end
        )
        local_points.append(slot_end)

        for global_start, global_end in zip(local_points, local_points[1:]):
            duration = global_end - global_start
            if duration <= 0.05:
                continue
            clone = MediaItem(**asdict(item))
            clone.start = item.start + (global_start - slot_start)
            clone.duration = duration
            if clone.kind == "video":
                clone.scale = (
                    max(1.0, float(item.scale))
                    if segment_index % 2 == 0
                    else max(1.0, float(item.scale)) * punch_scale
                )
            result.append(clone)
            segment_index += 1
        slot_cursor = slot_end
    return result


def apply_talk_rhythm(
    project: ProjectState,
    *,
    minimum_segment: float = 1.2,
    punch_scale: float = 1.035,
) -> dict[str, Any]:
    if project.profile != "TALKING_HEAD_EXPERT":
        raise ValueError("Punch rhythm chỉ áp dụng cho Talk / Chuyên gia.")
    if not project.timeline:
        raise ValueError("Timeline đang trống.")

    boundaries = _normalized_boundaries(
        project,
        minimum_segment=minimum_segment,
    )
    if not boundaries:
        return {
            "status": "NO_CHANGE",
            "segments": len(project.timeline),
            "punches": 0,
            "boundaries": [],
        }

    before_duration = sum(item.duration for item in project.timeline)
    project.timeline = _split_timeline(
        project.timeline,
        boundaries,
        punch_scale=punch_scale,
    )
    after_duration = sum(item.duration for item in project.timeline)
    if abs(before_duration - after_duration) > 0.02:
        raise RuntimeError("Talk rhythm làm lệch thời lượng timeline.")
    project.dirty = True
    return {
        "status": "DONE",
        "segments": len(project.timeline),
        "punches": max(0, len(project.timeline) - 1),
        "boundaries": [round(value, 3) for value in boundaries],
        "duration": round(after_duration, 3),
        "punch_scale": float(punch_scale),
    }


def apply_talk_rhythm_to_file(
    project_path: Path,
    *,
    minimum_segment: float = 1.2,
    punch_scale: float = 1.035,
) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-talk-rhythm",
    )
    result = apply_talk_rhythm(
        project,
        minimum_segment=minimum_segment,
        punch_scale=punch_scale,
    )
    if result["status"] == "DONE":
        project.save(project_path)
    result["project"] = str(project_path)
    result["checkpoint"] = str(checkpoint)
    return result
