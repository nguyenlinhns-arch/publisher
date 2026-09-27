from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .checkpoint import create_checkpoint
from .project import MediaItem, ProjectState

TRAVEL_PATTERN = (
    "visual_hook",
    "human",
    "work",
    "road_reset",
    "place",
    "detail",
    "life",
    "human",
    "detail",
    "emotion",
    "ending",
)

ROLE_FALLBACKS: dict[str, tuple[str, ...]] = {
    "visual_hook": ("place", "human", "road_reset"),
    "human": ("life", "emotion", "detail"),
    "work": ("human", "detail"),
    "road_reset": ("place", "detail"),
    "place": ("road_reset", "detail"),
    "detail": ("life", "place", "human"),
    "life": ("human", "detail", "place"),
    "emotion": ("human", "life", "detail"),
    "ending": ("emotion", "place", "human", "detail"),
}

ROLE_DURATION = {
    "visual_hook": 3.0,
    "work": 2.5,
    "road_reset": 3.0,
    "place": 3.4,
    "detail": 3.2,
    "life": 3.6,
    "human": 4.5,
    "emotion": 4.8,
    "ending": 5.5,
}


@dataclass(frozen=True, slots=True)
class StoryOptimizationReport:
    target_seconds: float
    duration: float
    scenes: int
    work_seconds: float
    work_ratio: float
    road_resets: int
    human_scenes: int
    ending_present: bool
    unique_sources: int
    repeated_sources: int
    roles: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_key(item: MediaItem) -> tuple[str, float, float]:
    return (
        str(Path(item.path)),
        round(float(item.start), 3),
        round(float(item.duration), 3),
    )


def _pick_best(
    media: list[MediaItem],
    used: set[tuple[str, float, float]],
    role: str,
    *,
    used_paths: dict[str, int],
) -> MediaItem | None:
    roles = (role, *ROLE_FALLBACKS.get(role, ()))
    best: tuple[float, MediaItem] | None = None
    for candidate in media:
        key = _candidate_key(candidate)
        if key in used:
            continue
        if candidate.role not in roles:
            continue
        role_rank = roles.index(candidate.role)
        path_count = used_paths.get(candidate.path, 0)
        diversity_penalty = min(0.24, path_count * 0.08)
        role_penalty = role_rank * 0.08
        score = float(candidate.score) - diversity_penalty - role_penalty
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else None


def _copy_with_duration(item: MediaItem, role: str, duration: float) -> MediaItem:
    clone = MediaItem(**asdict(item))
    clone.role = role
    clone.duration = max(0.5, min(float(item.duration), float(duration)))
    return clone


def optimize_travel_story(project: ProjectState) -> list[MediaItem]:
    source = list(project.media)
    if not source:
        return []

    target = max(45.0, min(90.0, float(project.target_seconds)))
    used: set[tuple[str, float, float]] = set()
    used_paths: dict[str, int] = {}
    timeline: list[MediaItem] = []
    total = 0.0
    work_seconds = 0.0

    # First pass creates a complete story arc before filling extra time.
    for role in TRAVEL_PATTERN:
        if total >= target:
            break
        picked = _pick_best(source, used, role, used_paths=used_paths)
        if picked is None:
            continue

        desired = ROLE_DURATION.get(role, 3.4)
        remaining = target - total
        duration = min(desired, picked.duration, remaining)
        if duration < 0.8:
            continue
        if role == "work":
            allowed_work = target * 0.35 - work_seconds
            duration = min(duration, max(0.0, allowed_work))
            if duration < 0.8:
                continue

        clone = _copy_with_duration(picked, role, duration)
        timeline.append(clone)
        used.add(_candidate_key(picked))
        used_paths[picked.path] = used_paths.get(picked.path, 0) + 1
        total += clone.duration
        if role == "work":
            work_seconds += clone.duration

    # Fill toward target with the most documentary-friendly roles, while
    # preserving work/admin as a minority.
    fill_roles = ("human", "place", "detail", "life", "road_reset", "emotion")
    while total < target:
        progress = False
        for role in fill_roles:
            if total >= target:
                break
            picked = _pick_best(source, used, role, used_paths=used_paths)
            if picked is None:
                continue
            remaining = target - total
            duration = min(
                ROLE_DURATION.get(role, 3.4),
                picked.duration,
                remaining,
            )
            if duration < 0.8:
                continue
            clone = _copy_with_duration(picked, role, duration)
            timeline.append(clone)
            used.add(_candidate_key(picked))
            used_paths[picked.path] = used_paths.get(picked.path, 0) + 1
            total += clone.duration
            progress = True
        if not progress:
            break

    # Ending should linger. If one exists earlier, move the best ending to the
    # tail while keeping hard-cut structure.
    ending_indices = [
        index for index, item in enumerate(timeline) if item.role == "ending"
    ]
    if ending_indices and ending_indices[-1] != len(timeline) - 1:
        ending = timeline.pop(ending_indices[-1])
        timeline.append(ending)

    return timeline


def analyze_story(timeline: list[MediaItem], target_seconds: float) -> StoryOptimizationReport:
    duration = sum(max(0.0, item.duration) for item in timeline)
    work_seconds = sum(
        max(0.0, item.duration)
        for item in timeline
        if item.role in {"work", "admin"}
    )
    paths = [item.path for item in timeline]
    unique = len(set(paths))
    return StoryOptimizationReport(
        target_seconds=round(float(target_seconds), 3),
        duration=round(duration, 3),
        scenes=len(timeline),
        work_seconds=round(work_seconds, 3),
        work_ratio=round(work_seconds / duration, 4) if duration else 0.0,
        road_resets=sum(1 for item in timeline if item.role == "road_reset"),
        human_scenes=sum(1 for item in timeline if item.role == "human"),
        ending_present=bool(timeline and timeline[-1].role == "ending"),
        unique_sources=unique,
        repeated_sources=max(0, len(paths) - unique),
        roles=tuple(item.role for item in timeline),
    )


def optimize_story(project: ProjectState) -> dict[str, Any]:
    if project.profile != "TRAVEL_DOCUMENTARY":
        raise ValueError("Story Optimizer 1.7 hiện áp dụng cho Travel / Công tác.")
    timeline = optimize_travel_story(project)
    if not timeline:
        raise ValueError("Không có đủ media để tối ưu story.")
    project.timeline = timeline
    project.dirty = True
    report = analyze_story(timeline, project.target_seconds)
    return {"status": "DONE", **report.to_dict()}


def optimize_story_to_file(project_path: Path) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-story-optimize",
    )
    result = optimize_story(project)
    project.save(project_path)
    result["project"] = str(project_path)
    result["checkpoint"] = str(checkpoint)
    result["revision"] = project.revision
    return result
