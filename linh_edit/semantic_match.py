from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .caption_planner import CaptionBlock, project_caption_plan
from .checkpoint import create_checkpoint
from .project import MediaItem, ProjectState


def _timeline_slots(project: ProjectState) -> list[tuple[float, float, int, MediaItem]]:
    cursor = 0.0
    result: list[tuple[float, float, int, MediaItem]] = []
    for index, item in enumerate(project.timeline):
        start = cursor
        end = cursor + max(0.0, item.duration)
        result.append((start, end, index, item))
        cursor = end
    return result


def _slot_at(
    slots: list[tuple[float, float, int, MediaItem]],
    timestamp: float,
) -> tuple[float, float, int, MediaItem] | None:
    for slot in slots:
        if slot[0] <= timestamp < slot[1]:
            return slot
    return slots[-1] if slots else None


def build_text_shot_report(
    project: ProjectState,
    *,
    coverage_target: float = 0.65,
) -> dict[str, Any]:
    blocks = project_caption_plan(
        project,
        coverage_target=coverage_target,
    )
    slots = _timeline_slots(project)
    rows: list[dict[str, Any]] = []
    matched = 0
    actionable = 0

    for block in blocks:
        midpoint = (block.start + block.end) / 2
        slot = _slot_at(slots, midpoint)
        if slot is None:
            continue
        _start, _end, index, item = slot
        desired = block.desired_role
        is_match = not desired or item.role == desired
        if is_match:
            matched += 1
        suggestion = None
        if desired and not is_match:
            candidates = [
                other_index
                for _s, _e, other_index, other in slots
                if other.role == desired
                and abs(other_index - index) <= 3
            ]
            if candidates:
                suggestion = min(
                    candidates,
                    key=lambda value: abs(value - index),
                )
                actionable += 1
        rows.append(
            {
                "caption": block.text,
                "start": block.start,
                "end": block.end,
                "desired_role": desired,
                "timeline_index": index,
                "timeline_role": item.role,
                "matched": is_match,
                "suggested_swap_index": suggestion,
            }
        )

    return {
        "status": "READY",
        "caption_blocks": len(blocks),
        "matched": matched,
        "actionable": actionable,
        "rows": rows,
    }


def _clone_for_slot(item: MediaItem, duration: float) -> MediaItem:
    payload = asdict(item)
    payload["duration"] = duration
    return MediaItem(**payload)


def apply_text_shot_matching(
    project: ProjectState,
    *,
    coverage_target: float = 0.65,
    max_distance: int = 3,
) -> dict[str, Any]:
    report = build_text_shot_report(
        project,
        coverage_target=coverage_target,
    )
    touched: set[int] = set()
    swaps: list[dict[str, Any]] = []

    for row in report["rows"]:
        desired = str(row["desired_role"] or "")
        if not desired or row["matched"]:
            continue
        left = int(row["timeline_index"])
        if left in touched or not 0 <= left < len(project.timeline):
            continue
        left_item = project.timeline[left]
        options: list[int] = []
        for right, candidate in enumerate(project.timeline):
            if right == left or right in touched:
                continue
            if abs(right - left) > max_distance:
                continue
            if candidate.role != desired:
                continue
            # Preserve exact timeline slot lengths. Both source snippets must
            # be long enough to occupy the other's existing slot.
            if candidate.duration + 1e-6 < left_item.duration:
                continue
            right_slot_duration = project.timeline[right].duration
            if left_item.duration + 1e-6 < right_slot_duration:
                continue
            options.append(right)
        if not options:
            continue

        right = min(options, key=lambda value: abs(value - left))
        right_item = project.timeline[right]
        left_duration = left_item.duration
        right_duration = right_item.duration
        project.timeline[left] = _clone_for_slot(right_item, left_duration)
        project.timeline[right] = _clone_for_slot(left_item, right_duration)
        touched.update({left, right})
        swaps.append(
            {
                "from": right,
                "to": left,
                "desired_role": desired,
                "caption": row["caption"],
            }
        )

    project.dirty = bool(swaps) or project.dirty
    return {
        "status": "DONE",
        "swaps": swaps,
        "swap_count": len(swaps),
        "before": report,
        "after": build_text_shot_report(
            project,
            coverage_target=coverage_target,
        ),
    }


def apply_text_shot_matching_to_file(
    project_path: Path,
    *,
    coverage_target: float = 0.65,
    max_distance: int = 3,
) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-text-shot-match",
    )
    result = apply_text_shot_matching(
        project,
        coverage_target=coverage_target,
        max_distance=max_distance,
    )
    if result["swap_count"]:
        project.save(project_path)
    result["project"] = str(project_path)
    result["checkpoint"] = str(checkpoint)
    return result
