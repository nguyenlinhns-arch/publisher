from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .media import audit_media_info, default_segment_duration, infer_role, probe
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


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def import_media(paths: list[Path]) -> list[MediaItem]:
    items: list[MediaItem] = []
    for path in paths:
        path = path.expanduser().resolve()
        role = infer_role(path)
        if not path.is_file():
            raise RuntimeError(f"Không tìm thấy media: {path}")

        if path.suffix.lower() in IMAGE_EXTENSIONS:
            items.append(
                MediaItem(
                    path=str(path),
                    kind="image",
                    role=role,
                    start=0.0,
                    duration=4.0,
                    score=0.55,
                    motion="slow_zoom",
                    keep_audio=False,
                    source_gain=0.0,
                )
            )
            continue

        info = probe(path)
        audit = audit_media_info(info)
        if audit.reject:
            raise RuntimeError(
                f"Loại media {path.name}: " + ", ".join(audit.reasons)
            )
        duration = default_segment_duration(role, info.duration)
        items.append(
            MediaItem(
                path=str(info.path),
                kind="video",
                role=role,
                start=0.0,
                duration=duration,
                score=audit.score,
                motion="none",
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
            copied = MediaItem(**asdict(picked))
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
    source = sorted(project.media, key=lambda x: x.score, reverse=True)
    if not source:
        return timeline

    allow_reuse = project.profile == "EXPLAINER_NEWS"
    cycle = 0
    while total < target:
        made_progress = False
        for item in source:
            if total >= target:
                break
            copied = MediaItem(**asdict(item))
            copied.duration = min(copied.duration, target - total)
            if copied.duration < 0.5:
                continue
            if project.profile == "TALKING_HEAD_EXPERT":
                copied.keep_audio = True
                copied.source_gain = 1.0
            timeline.append(copied)
            total += copied.duration
            made_progress = True
        cycle += 1
        if not allow_reuse or not made_progress or cycle >= 20:
            break
    return timeline


def build_rough_cut(project: ProjectState) -> list[MediaItem]:
    if project.profile == "TRAVEL_DOCUMENTARY":
        from .story_optimizer import optimize_travel_story

        return optimize_travel_story(project)
    return _simple_rough_cut(project)
