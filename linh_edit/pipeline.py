from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .caption_planner import apply_selective_captions
from .checkpoint import create_checkpoint
from .engine_adapter import render_project
from .loudness import auto_balance_project
from .planner import build_rough_cut
from .project import ProjectState
from .review_gate import review_status
from .semantic_match import apply_text_shot_matching
from .speech_rhythm import apply_talk_rhythm
from .story_optimizer import optimize_story
from .validation import validate_project


def _safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "-", value or "").strip(" .-")
    return value[:120] or "LinhEdit_Final"


def _receipt_path(project_path: Path) -> Path:
    name = project_path.name
    if name.endswith(".linhedit.json"):
        name = name[: -len(".linhedit.json")]
    else:
        name = project_path.stem
    return project_path.with_name(name + "_pipeline_receipt.json")


def run_optimized_pipeline(
    project_path: Path,
    *,
    render: bool = True,
    preview: bool = False,
    output: Path | None = None,
) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-optimize-all",
    )

    steps: list[dict[str, Any]] = []

    if not project.timeline and project.media:
        timeline = build_rough_cut(project)
        if not timeline:
            raise ValueError("Không tạo được rough cut từ media hiện có.")
        project.timeline = timeline
        project.dirty = True
        steps.append(
            {
                "step": "rough_cut",
                "status": "DONE",
                "scenes": len(timeline),
                "duration": round(sum(item.duration for item in timeline), 3),
            }
        )

    if project.profile == "TRAVEL_DOCUMENTARY" and project.media:
        try:
            result = optimize_story(project)
            steps.append({"step": "story_optimize", "status": "DONE", **result})
        except Exception as exc:
            steps.append(
                {
                    "step": "story_optimize",
                    "status": "SKIPPED",
                    "reason": str(exc),
                }
            )

    if project.profile == "TALKING_HEAD_EXPERT" and project.timeline:
        try:
            result = apply_talk_rhythm(project)
            steps.append({"step": "talk_rhythm", **result})
        except Exception as exc:
            steps.append(
                {
                    "step": "talk_rhythm",
                    "status": "SKIPPED",
                    "reason": str(exc),
                }
            )

    if project.transcript.strip():
        try:
            result = apply_selective_captions(
                project,
                coverage_target=project.caption_coverage_target,
                replace_existing=True,
            )
            steps.append({"step": "selective_captions", **result})
        except Exception as exc:
            steps.append(
                {
                    "step": "selective_captions",
                    "status": "SKIPPED",
                    "reason": str(exc),
                }
            )

        if project.profile in {"TRAVEL_DOCUMENTARY", "DIRECT_RECRUITMENT"}:
            try:
                result = apply_text_shot_matching(
                    project,
                    coverage_target=project.caption_coverage_target,
                    max_distance=3,
                )
                steps.append(
                    {
                        "step": "text_shot_match",
                        "status": result["status"],
                        "swap_count": result["swap_count"],
                    }
                )
            except Exception as exc:
                steps.append(
                    {
                        "step": "text_shot_match",
                        "status": "SKIPPED",
                        "reason": str(exc),
                    }
                )

    if project.voiceover or project.music:
        try:
            result = auto_balance_project(project)
            steps.append(
                {
                    "step": "audio_auto_master",
                    "status": result["status"],
                    "voice": result["voice"],
                    "music": result["music"],
                }
            )
        except Exception as exc:
            steps.append(
                {
                    "step": "audio_auto_master",
                    "status": "SKIPPED",
                    "reason": str(exc),
                }
            )

    report = validate_project(project, deep=False)
    if report.errors:
        summary = "; ".join(item.message for item in report.errors[:8])
        raise RuntimeError("Pipeline tạo project chưa hợp lệ: " + summary)

    project.dirty = True
    project.save(project_path)

    rendered = ""
    editorial_qa = ""
    if render:
        if output is None:
            root = Path(project.output_dir).expanduser() if project.output_dir else project_path.parent
            root.mkdir(parents=True, exist_ok=True)
            suffix = "_PREVIEW.mp4" if preview else ".mp4"
            output = root / (_safe_name(project.title or project.name) + suffix)
        result_path = render_project(
            project,
            output,
            preview=preview,
            include_audio=True,
        )
        rendered = str(result_path)
        candidate = result_path.with_suffix(".editorial_qa.json")
        if candidate.is_file():
            editorial_qa = str(candidate)

    payload = {
        "schema": "linh-edit.pipeline.v1",
        "status": "TECHNICAL_DONE" if rendered else "OPTIMIZED",
        "project": str(project_path),
        "checkpoint": str(checkpoint),
        "revision": project.revision,
        "content_revision": project.content_revision,
        "steps": steps,
        "validation": report.to_dict(),
        "rendered": rendered,
        "editorial_qa": editorial_qa,
        "review": review_status(project),
        "next_required": "3_PASS_PLAYBACK_REVIEW",
    }
    receipt = _receipt_path(project_path)
    temp = receipt.with_suffix(receipt.suffix + ".partial")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(receipt)
    payload["receipt"] = str(receipt)
    return payload
