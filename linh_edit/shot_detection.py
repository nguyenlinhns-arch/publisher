from __future__ import annotations

import re
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
from .media import probe_duration
from .tools import resolve_tool

PTS_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True, slots=True)
class ShotSpan:
    index: int
    start: float
    end: float
    duration: float


def _normalize_boundaries(
    values: list[float],
    duration: float,
    *,
    min_gap: float,
) -> list[float]:
    points = [0.0]
    for raw in sorted(values):
        value = max(0.0, min(float(duration), float(raw)))
        if value - points[-1] >= min_gap:
            points.append(value)
    if duration - points[-1] < min_gap and len(points) > 1:
        points[-1] = duration
    elif duration > points[-1]:
        points.append(duration)
    if points[-1] != duration:
        points[-1] = duration
    return points


def spans_from_boundaries(
    boundaries: list[float],
    duration: float,
    *,
    min_shot_seconds: float = 0.35,
) -> tuple[ShotSpan, ...]:
    points = _normalize_boundaries(
        boundaries,
        duration,
        min_gap=max(0.05, min_shot_seconds),
    )
    result: list[ShotSpan] = []
    for start, end in zip(points, points[1:]):
        if end - start < min_shot_seconds:
            continue
        result.append(
            ShotSpan(
                index=len(result) + 1,
                start=round(start, 3),
                end=round(end, 3),
                duration=round(end - start, 3),
            )
        )
    if not result and duration > 0:
        result.append(
            ShotSpan(
                index=1,
                start=0.0,
                end=round(duration, 3),
                duration=round(duration, 3),
            )
        )
    return tuple(result)


def detect_shots(
    source: Path,
    *,
    threshold: float = 0.32,
    min_gap: float = 0.45,
    force: bool = False,
) -> tuple[ShotSpan, ...]:
    source = source.expanduser().resolve()
    cache_dir = source_cache_dir(source)
    manifest = cache_dir / "shots.json"
    payload = read_json(manifest)

    threshold = max(0.05, min(0.90, float(threshold)))
    min_gap = max(0.10, float(min_gap))

    if (
        not force
        and cache_matches(payload, source)
        and abs(float(payload.get("threshold", -1)) - threshold) < 0.0001
        and abs(float(payload.get("min_gap", -1)) - min_gap) < 0.0001
    ):
        shots = payload.get("shots") or []
        return tuple(ShotSpan(**item) for item in shots)

    duration = probe_duration(source)
    filter_expr = f"select='gt(scene,{threshold:.4f})',showinfo"
    completed = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(source),
            "-filter:v",
            filter_expr,
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stderr or f"Không detect được shot: {source.name}")[-3000:]
        )

    values = [float(match.group(1)) for match in PTS_RE.finditer(completed.stderr)]
    spans = spans_from_boundaries(values, duration, min_shot_seconds=min_gap)
    payload = {
        "schema": CACHE_SCHEMA,
        "kind": "shot-detection",
        "shot_version": 1,
        "source_signature": asdict(source_signature(source)),
        "threshold": threshold,
        "min_gap": min_gap,
        "duration": duration,
        "shots": [asdict(item) for item in spans],
    }
    write_json_atomic(manifest, payload)
    return spans
