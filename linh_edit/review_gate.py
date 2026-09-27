from __future__ import annotations

from pathlib import Path
from typing import Any

from .project import ProjectState

VALID_REVIEW_STATUS = {"PENDING", "PASS", "FAIL"}
STAGE_FIELD = {
    "visual": "review_visual",
    "audio": "review_audio",
    "full": "review_full_playback",
}


def review_status(project: ProjectState) -> dict[str, Any]:
    current = project.review_is_current()
    ready = project.ready_to_publish()
    return {
        "status": "READY_TO_PUBLISH" if ready else "PENDING_REVIEW",
        "content_revision": project.content_revision,
        "review_content_revision": project.review_content_revision,
        "review_current": current,
        "visual": project.review_visual,
        "audio": project.review_audio,
        "full_playback": project.review_full_playback,
        "ready_to_publish": ready,
    }


def set_review_stage(
    project_path: Path,
    *,
    stage: str,
    value: str,
) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    stage = stage.strip().lower()
    value = value.strip().upper()
    if stage not in STAGE_FIELD:
        raise ValueError("stage phải là visual, audio hoặc full.")
    if value not in VALID_REVIEW_STATUS:
        raise ValueError("review status phải là PENDING, PASS hoặc FAIL.")

    # If editorial content changed since the previous review cycle, never
    # carry PASS values from that older edit into the new cycle.
    if project.review_content_revision != project.content_revision:
        project.review_visual = "PENDING"
        project.review_audio = "PENDING"
        project.review_full_playback = "PENDING"
    setattr(project, STAGE_FIELD[stage], value)
    project.review_content_revision = project.content_revision
    project.dirty = False
    project.save(project_path)
    result = review_status(project)
    result["project"] = str(project_path)
    result["revision"] = project.revision
    return result


def reset_review(project_path: Path) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    project.review_visual = "PENDING"
    project.review_audio = "PENDING"
    project.review_full_playback = "PENDING"
    project.review_content_revision = project.content_revision
    project.dirty = False
    project.save(project_path)
    result = review_status(project)
    result["project"] = str(project_path)
    result["revision"] = project.revision
    return result
