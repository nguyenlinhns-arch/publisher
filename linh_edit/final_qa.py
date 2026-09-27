from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .loudness import measure_loudness
from .media import probe
from .project import ProjectState
from .review_gate import review_status
from .tools import resolve_tool

BLACK_RE = re.compile(
    r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)"
)
SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


@dataclass(frozen=True, slots=True)
class Span:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict[str, float]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
        }


def _run_filter(path: Path, filter_text: str) -> str:
    completed = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf" if filter_text.startswith("blackdetect") else "-af",
            filter_text,
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
        raise RuntimeError((completed.stderr or "FFmpeg QA filter failed")[-3000:])
    return completed.stderr


def detect_black_spans(path: Path) -> tuple[Span, ...]:
    text = _run_filter(
        path.expanduser().resolve(),
        "blackdetect=d=0.40:pic_th=0.98:pix_th=0.10",
    )
    return tuple(
        Span(float(match.group("start")), float(match.group("end")))
        for match in BLACK_RE.finditer(text)
    )


def detect_silence_spans(path: Path) -> tuple[Span, ...]:
    text = _run_filter(
        path.expanduser().resolve(),
        "silencedetect=noise=-45dB:d=1.50",
    )
    starts = [float(match.group(1)) for match in SILENCE_START_RE.finditer(text)]
    ends = [float(match.group(1)) for match in SILENCE_END_RE.finditer(text)]
    return tuple(
        Span(start, end)
        for start, end in zip(starts, ends)
        if end > start
    )


def project_edit_metrics(project: ProjectState) -> dict[str, Any]:
    timeline = project.timeline
    duration = sum(max(0.0, item.duration) for item in timeline)
    shot_count = len(timeline)
    shot_durations = [max(0.0, item.duration) for item in timeline]
    work_seconds = sum(
        item.duration for item in timeline if item.role in {"work", "admin"}
    )
    caption_seconds = sum(
        max(0.0, item.end - item.start)
        for item in project.texts
        if item.role == "caption"
    )
    hook_roles = {
        item.role
        for item in project.texts
        if item.role in {"context", "main", "keyword"}
    }
    paths = [item.path for item in timeline]
    repeated_consecutive = sum(
        1 for left, right in zip(paths, paths[1:]) if left == right
    )
    unique_sources = len(set(paths))

    warnings: list[str] = []
    average_shot = duration / shot_count if shot_count else 0.0
    if project.profile == "TRAVEL_DOCUMENTARY":
        if duration and work_seconds / duration > 0.40:
            warnings.append("work_admin_ratio_high")
        if duration >= 30 and not any(
            item.role == "road_reset" for item in timeline
        ):
            warnings.append("missing_road_reset")
        if timeline and timeline[-1].duration < 3.5:
            warnings.append("ending_hold_short")
        if average_shot and not 2.2 <= average_shot <= 5.2:
            warnings.append("travel_average_shot_outside_reference")
    if repeated_consecutive:
        warnings.append("consecutive_same_source")
    if project.transcript.strip() and duration:
        coverage = caption_seconds / duration
        if coverage > 0.85:
            warnings.append("caption_coverage_too_dense")
        elif coverage < 0.35 and project.texts:
            warnings.append("caption_coverage_low")
    else:
        coverage = 0.0
    if project.texts and hook_roles != {"context", "main", "keyword"}:
        warnings.append("hook_layers_incomplete")

    return {
        "duration": round(duration, 3),
        "shot_count": shot_count,
        "average_shot_seconds": round(average_shot, 3),
        "min_shot_seconds": round(min(shot_durations), 3) if shot_durations else 0.0,
        "max_shot_seconds": round(max(shot_durations), 3) if shot_durations else 0.0,
        "work_seconds": round(work_seconds, 3),
        "work_ratio": round(work_seconds / duration, 4) if duration else 0.0,
        "road_resets": sum(1 for item in timeline if item.role == "road_reset"),
        "human_scenes": sum(1 for item in timeline if item.role == "human"),
        "emotion_scenes": sum(1 for item in timeline if item.role == "emotion"),
        "unique_sources": unique_sources,
        "repeated_consecutive_sources": repeated_consecutive,
        "caption_seconds": round(caption_seconds, 3),
        "caption_coverage": round(coverage, 4),
        "hook_roles": sorted(hook_roles),
        "warnings": warnings,
    }


def analyze_render(
    output: Path,
    project: ProjectState,
    *,
    preview: bool = False,
) -> dict[str, Any]:
    output = output.expanduser().resolve()
    info = probe(output)
    errors: list[str] = []
    warnings: list[str] = []

    black_spans: tuple[Span, ...] = ()
    silence_spans: tuple[Span, ...] = ()
    try:
        black_spans = detect_black_spans(output)
    except Exception as exc:
        warnings.append(f"blackdetect_unavailable:{type(exc).__name__}")

    loudness = None
    if info.has_audio:
        try:
            silence_spans = detect_silence_spans(output)
        except Exception as exc:
            warnings.append(f"silencedetect_unavailable:{type(exc).__name__}")
        try:
            measured = measure_loudness(output)
            loudness = measured.to_dict()
            if measured.integrated_lufs < -18.0 or measured.integrated_lufs > -10.0:
                warnings.append("final_loudness_outside_social_reference")
            if measured.true_peak_dbfs > -0.2:
                warnings.append("true_peak_too_hot")
        except Exception as exc:
            warnings.append(f"loudness_measure_unavailable:{type(exc).__name__}")

    expected_duration = sum(item.duration for item in project.timeline)
    if abs(info.duration - expected_duration) > 0.25:
        errors.append("output_duration_mismatch")
    if not preview and (info.width, info.height) != (1080, 1920):
        errors.append("unexpected_final_geometry")
    if not 29.5 <= info.fps <= 30.5:
        errors.append("unexpected_output_fps")
    if any(span.duration >= 0.6 for span in black_spans):
        warnings.append("black_span_detected")

    edit = project_edit_metrics(project)
    warnings.extend(edit["warnings"])

    return {
        "schema": "linh-edit.editorial-qa.v1",
        "auto_checks_passed": not errors,
        "preview": bool(preview),
        "output": str(output),
        "duration": round(info.duration, 3),
        "width": info.width,
        "height": info.height,
        "fps": round(info.fps, 3),
        "video_codec": info.video_codec,
        "audio_codec": info.audio_codec,
        "black_spans": [item.to_dict() for item in black_spans],
        "silence_spans": [item.to_dict() for item in silence_spans],
        "loudness": loudness,
        "edit_metrics": edit,
        "review": review_status(project),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "editorial_review_required": True,
    }


def write_editorial_qa(
    output: Path,
    project: ProjectState,
    *,
    preview: bool = False,
) -> Path:
    report = analyze_render(output, project, preview=preview)
    target = output.with_suffix(".editorial_qa.json")
    temp = target.with_suffix(target.suffix + ".partial")
    temp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(target)
    return target
