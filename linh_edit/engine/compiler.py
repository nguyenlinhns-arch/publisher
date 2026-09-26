from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import AudioSpec, ClipSpec, EditPlan, ExportSpec
from .profiles import get_profile


@dataclass(frozen=True, slots=True)
class FootageCandidate:
    source: Path
    start: float
    available_duration: float
    role: str
    score: float = 0.5
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    keep_ambience: bool = False


TRAVEL_ROLE_ORDER = (
    "visual_hook",
    "human",
    "work",
    "road_reset",
    "place",
    "detail",
    "human",
    "road_reset",
    "life",
    "detail",
    "emotion",
    "ending",
)


def _desired_duration(role: str) -> float:
    if role in {"work", "admin"}:
        return 2.5
    if role in {"human", "emotion", "ending"}:
        return 4.8
    if role == "road_reset":
        return 3.0
    return 3.4


def _pick(
    candidates: list[FootageCandidate],
    role: str,
    used: set[tuple[Path, float]],
) -> FootageCandidate | None:
    pool = [
        item
        for item in candidates
        if item.role == role and (item.source, item.start) not in used
    ]
    if not pool and role in {"life", "emotion"}:
        pool = [
            item
            for item in candidates
            if item.role in {"human", "detail", "life", "emotion"}
            and (item.source, item.start) not in used
        ]
    if not pool:
        return None
    return max(pool, key=lambda item: (item.score, item.available_duration))


def compile_travel_plan(
    candidates: Iterable[FootageCandidate],
    *,
    target_seconds: float = 75.0,
    voiceover: Path | None = None,
    music: Path | None = None,
    title: str = "",
) -> EditPlan:
    profile = get_profile("TRAVEL_DOCUMENTARY")
    target_seconds = max(
        profile.target_min_seconds,
        min(profile.target_max_seconds, target_seconds),
    )
    items = list(candidates)
    if not items:
        raise ValueError("no footage candidates")

    clips: list[ClipSpec] = []
    used: set[tuple[Path, float]] = set()
    total = 0.0

    while total < target_seconds:
        made_progress = False
        for role in TRAVEL_ROLE_ORDER:
            if total >= target_seconds:
                break
            picked = _pick(items, role, used)
            if picked is None:
                continue
            duration = min(
                picked.available_duration,
                _desired_duration(role),
                target_seconds - total,
            )
            if duration < 1.0:
                continue
            clips.append(
                ClipSpec(
                    source=picked.source,
                    start=picked.start,
                    duration=duration,
                    role=role,
                    x=picked.x,
                    y=picked.y,
                    scale=picked.scale,
                    mute_source_audio=not picked.keep_ambience,
                )
            )
            used.add((picked.source, picked.start))
            total += duration
            made_progress = True
        if not made_progress:
            break

    if total < min(30.0, target_seconds * 0.6):
        raise ValueError("insufficient selected footage for a coherent travel cut")

    return EditPlan(
        profile="TRAVEL_DOCUMENTARY",
        clips=tuple(clips),
        audio=AudioSpec(
            voiceover=voiceover,
            music=music,
            music_gain=0.14,
            source_ambience_gain=0.10,
            ending_music_only_seconds=profile.ending_hold_seconds,
        ),
        export=ExportSpec(width=1080, height=1920, fps=30, crf=18),
        title=title,
    )
