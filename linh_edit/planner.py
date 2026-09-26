from __future__ import annotations

from pathlib import Path

from .media import default_segment_duration, infer_role, probe
from .project import MediaItem, ProjectState


TRAVEL_SEQUENCE = (
    "visual_hook",
    "human",
    "work",
    "road_reset",
    "place",
    "detail",
    "life",
    "road_reset",
    "human",
    "detail",
    "emotion",
    "ending",
)


def import_media(paths: list[Path]) -> list[MediaItem]:
    items: list[MediaItem] = []
    for path in paths:
        info = probe(path)
        role = infer_role(path)
        duration = default_segment_duration(role, info.duration)
        items.append(
            MediaItem(
                path=str(info.path),
                role=role,
                start=0.0,
                duration=duration,
                score=0.5,
                keep_audio=False,
                source_gain=0.10,
            )
        )
    return items


def _travel_rough_cut(project: ProjectState) -> list[MediaItem]:
    source = list(project.media)
    used: set[int] = set()
    timeline: list[MediaItem] = []
    total = 0.0
    target = max(45.0, min(90.0, project.target_seconds))

    while total < target:
        progress = False
        for role in TRAVEL_SEQUENCE:
            if total >= target:
                break
            choices = [
                (i, item)
                for i, item in enumerate(source)
                if i not in used and item.role == role
            ]
            if not choices and role in {"emotion", "ending", "human", "life"}:
                choices = [
                    (i, item)
                    for i, item in enumerate(source)
                    if i not in used and item.role in {"human", "life", "detail", "place"}
                ]
            if not choices:
                continue
            i, picked = max(choices, key=lambda pair: pair[1].score)
            remaining = target - total
            duration = min(picked.duration, remaining)
            if duration < 1.0:
                continue
            copied = MediaItem(**vars(picked))
            copied.duration = duration
            if role == "visual_hook":
                copied.role = "visual_hook"
            elif role == "ending":
                copied.role = "ending"
            timeline.append(copied)
            used.add(i)
            total += duration
            progress = True
        if not progress:
            break
    return timeline


def _simple_rough_cut(project: ProjectState) -> list[MediaItem]:
    target = max(10.0, min(90.0, project.target_seconds))
    timeline: list[MediaItem] = []
    total = 0.0
    for item in sorted(project.media, key=lambda x: x.score, reverse=True):
        if total >= target:
            break
        copied = MediaItem(**vars(item))
        copied.duration = min(copied.duration, target - total)
        if copied.duration < 0.5:
            continue
        if project.profile == "TALKING_HEAD_EXPERT":
            copied.keep_audio = True
            copied.source_gain = 1.0
        timeline.append(copied)
        total += copied.duration
    return timeline


def build_rough_cut(project: ProjectState) -> list[MediaItem]:
    if project.profile == "TRAVEL_DOCUMENTARY":
        return _travel_rough_cut(project)
    return _simple_rough_cut(project)
