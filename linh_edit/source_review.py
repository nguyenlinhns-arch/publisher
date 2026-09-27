from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .checkpoint import create_checkpoint
from .contact_sheet import extract_contact_sheet
from .media import MediaAudit, audit_media_info, infer_role, probe
from .project import MediaItem, ProjectState
from .visual_metrics import (
    analyze_frame,
    annotate_duplicate_groups,
    extract_contact_sheet_tiles,
)

REVIEW_SCHEMA = "linh-edit.source-review.v2"
REVIEW_DECISIONS = {"PENDING", "SHORTLIST", "KEEP", "REJECT"}


@dataclass(frozen=True, slots=True)
class CandidateWindow:
    index: int
    center: float
    start: float
    end: float
    duration: float
    frame: str = ""
    brightness: float = 0.0
    contrast: float = 0.0
    edge_energy: float = 0.0
    technical_score: float = 0.0
    duplicate_of: int | None = None
    warnings: tuple[str, ...] = ()
    decision: str = "PENDING"
    review_note: str = ""
    status: str = "PENDING_VISUAL_REVIEW"


@dataclass(frozen=True, slots=True)
class SourceReviewItem:
    source: str
    contact_sheet: str
    duration: float
    width: int
    height: int
    fps: float
    audit_score: float
    audit_reject: bool
    audit_reasons: tuple[str, ...]
    audit_warnings: tuple[str, ...]
    candidates: tuple[CandidateWindow, ...]
    visual_review: str = "PENDING"
    notes: str = (
        "Điểm kỹ thuật chỉ hỗ trợ sàng lọc. Rung, motion blur, crop mặt, "
        "hành động, cảm xúc và bố cục vẫn cần duyệt hình."
    )


def _safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-")
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{stem[:70] or 'media'}-{digest}"


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".partial")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def candidate_windows(
    duration: float,
    *,
    count: int = 12,
    segment_seconds: float = 3.4,
) -> tuple[CandidateWindow, ...]:
    duration = max(0.0, float(duration))
    if duration <= 0:
        return ()
    count = max(1, min(24, int(count)))
    segment_seconds = max(0.5, float(segment_seconds))

    if duration <= segment_seconds:
        return (
            CandidateWindow(
                index=1,
                center=round(duration / 2, 3),
                start=0.0,
                end=round(duration, 3),
                duration=round(duration, 3),
            ),
        )

    margin = min(segment_seconds / 2, duration * 0.08)
    left = margin
    right = max(left, duration - margin)
    if count == 1:
        centers = [duration / 2]
    else:
        centers = [
            left + (right - left) * index / (count - 1)
            for index in range(count)
        ]

    result: list[CandidateWindow] = []
    for index, center in enumerate(centers, start=1):
        start = max(
            0.0,
            min(duration - segment_seconds, center - segment_seconds / 2),
        )
        end = min(duration, start + segment_seconds)
        result.append(
            CandidateWindow(
                index=index,
                center=round(center, 3),
                start=round(start, 3),
                end=round(end, 3),
                duration=round(end - start, 3),
            )
        )
    return tuple(result)


def _enrich_candidates(
    base: tuple[CandidateWindow, ...],
    frames: tuple[Path, ...],
) -> tuple[CandidateWindow, ...]:
    metrics = tuple(analyze_frame(path) for path in frames)
    duplicate_map = annotate_duplicate_groups(metrics)
    result: list[CandidateWindow] = []
    for index, item in enumerate(base):
        if index >= len(metrics):
            result.append(item)
            continue
        metric = metrics[index]
        duplicate_of = duplicate_map[index]
        score = metric.technical_score
        warnings = list(metric.warnings)
        if duplicate_of is not None:
            score = max(0.0, score - 0.18)
            warnings.append(f"near_duplicate_of_{duplicate_of}")
        result.append(
            CandidateWindow(
                index=item.index,
                center=item.center,
                start=item.start,
                end=item.end,
                duration=item.duration,
                frame=str(frames[index]),
                brightness=metric.brightness,
                contrast=metric.contrast,
                edge_energy=metric.edge_energy,
                technical_score=round(score, 4),
                duplicate_of=duplicate_of,
                warnings=tuple(warnings),
            )
        )
    return tuple(result)


def review_video(
    source: Path,
    output_dir: Path,
    *,
    tiles: int = 12,
    columns: int = 4,
    candidate_seconds: float = 3.4,
) -> SourceReviewItem:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"Không tìm thấy footage: {source}")

    info = probe(source)
    audit: MediaAudit = audit_media_info(info)
    target_dir = output_dir / _safe_stem(source)
    target_dir.mkdir(parents=True, exist_ok=True)

    sheet = target_dir / "source_contact_sheet.jpg"
    extract_contact_sheet(
        source,
        sheet,
        tiles=tiles,
        columns=columns,
    )
    base_candidates = candidate_windows(
        info.duration,
        count=tiles,
        segment_seconds=candidate_seconds,
    )
    frames = extract_contact_sheet_tiles(
        sheet,
        target_dir / "candidates",
        tiles=len(base_candidates),
        columns=columns,
    )
    candidates = _enrich_candidates(base_candidates, frames)

    item = SourceReviewItem(
        source=str(source),
        contact_sheet=str(sheet),
        duration=round(info.duration, 3),
        width=info.width,
        height=info.height,
        fps=round(info.fps, 3),
        audit_score=audit.score,
        audit_reject=audit.reject,
        audit_reasons=audit.reasons,
        audit_warnings=audit.warnings,
        candidates=candidates,
    )
    _atomic_json_write(
        target_dir / "review.json",
        {
            "schema": REVIEW_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **asdict(item),
        },
    )
    return item


def build_source_review(
    sources: Iterable[Path],
    output_dir: Path,
    *,
    tiles: int = 12,
    columns: int = 4,
    candidate_seconds: float = 3.4,
) -> Path:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    items: list[SourceReviewItem] = []
    errors: list[dict[str, str]] = []
    for raw in sources:
        source = raw.expanduser().resolve()
        try:
            items.append(
                review_video(
                    source,
                    output_dir,
                    tiles=tiles,
                    columns=columns,
                    candidate_seconds=candidate_seconds,
                )
            )
        except Exception as exc:
            errors.append({"source": str(source), "error": str(exc)})

    if not items:
        detail = "; ".join(item["error"] for item in errors[:5])
        raise RuntimeError("Không tạo được source review. " + detail)

    manifest = output_dir / "source_review_manifest.json"
    _atomic_json_write(
        manifest,
        {
            "schema": REVIEW_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [asdict(item) for item in items],
            "errors": errors,
            "policy": {
                "technical_audit": "AUTOMATED",
                "visual_metrics": "HEURISTIC_RANKING_ONLY",
                "visual_quality": "PENDING_HUMAN_OR_VISION_REVIEW",
                "auto_accept_visual": False,
                "promotion_requires": "KEEP",
            },
        },
    )
    return manifest


def load_review_manifest(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Source Review manifest phải là JSON object.")
    if payload.get("schema") not in {
        "linh-edit.source-review.v1",
        REVIEW_SCHEMA,
    }:
        raise ValueError("Source Review schema không hỗ trợ.")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Source Review manifest không có items.")
    return payload


def _candidate_ref(
    payload: dict[str, Any],
    *,
    item_index: int,
    candidate_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    items = payload["items"]
    if not 1 <= item_index <= len(items):
        raise ValueError("item_index ngoài phạm vi.")
    item = items[item_index - 1]
    candidates = item.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Review item chưa có candidates.")
    if not 1 <= candidate_index <= len(candidates):
        raise ValueError("candidate_index ngoài phạm vi.")
    return item, candidates[candidate_index - 1]


def mark_candidate_review(
    manifest: Path,
    *,
    item_index: int,
    candidate_index: int,
    decision: str,
    note: str = "",
) -> Path:
    manifest = manifest.expanduser().resolve()
    payload = load_review_manifest(manifest)
    decision = decision.strip().upper()
    if decision not in REVIEW_DECISIONS:
        raise ValueError(
            "decision phải là: " + ", ".join(sorted(REVIEW_DECISIONS))
        )
    _item, candidate = _candidate_ref(
        payload,
        item_index=item_index,
        candidate_index=candidate_index,
    )
    candidate["decision"] = decision
    candidate["review_note"] = note.strip()
    candidate["status"] = (
        "VISUAL_REVIEWED"
        if decision != "PENDING"
        else "PENDING_VISUAL_REVIEW"
    )
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json_write(manifest, payload)
    return manifest


def promote_review_candidate(
    manifest: Path,
    project_path: Path,
    *,
    item_index: int,
    candidate_index: int,
    role: str | None = None,
    to_timeline: bool = True,
) -> dict[str, Any]:
    manifest = manifest.expanduser().resolve()
    project_path = project_path.expanduser().resolve()
    payload = load_review_manifest(manifest)
    item, candidate = _candidate_ref(
        payload,
        item_index=item_index,
        candidate_index=candidate_index,
    )
    if str(candidate.get("decision") or "PENDING").upper() != "KEEP":
        raise ValueError("Candidate phải được đánh dấu KEEP trước khi promote.")
    if bool(item.get("audit_reject")):
        raise ValueError("Footage bị technical audit loại nên không được promote.")

    source = Path(str(item["source"])).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Không tìm thấy footage: {source}")

    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-review-promote",
    )
    chosen_role = (role or infer_role(source)).strip() or "detail"
    score = float(candidate.get("technical_score") or item.get("audit_score") or 0.5)
    keep_audio = project.profile == "TALKING_HEAD_EXPERT"
    media = MediaItem(
        path=str(source),
        kind="video",
        role=chosen_role,
        start=float(candidate["start"]),
        duration=float(candidate["duration"]),
        score=max(0.0, min(1.0, score)),
        motion="none",
        keep_audio=keep_audio,
        source_gain=1.0 if keep_audio else 0.10,
    )

    duplicate = any(
        existing.path == media.path
        and abs(existing.start - media.start) < 0.02
        and abs(existing.duration - media.duration) < 0.02
        for existing in project.media
    )
    if not duplicate:
        project.media.append(media)
    if to_timeline:
        project.timeline.append(MediaItem(**asdict(media)))

    project.dirty = True
    project.save(project_path)

    candidate["status"] = "PROMOTED"
    candidate["promoted_project"] = str(project_path)
    candidate["promoted_role"] = chosen_role
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json_write(manifest, payload)

    return {
        "status": "DONE",
        "project": str(project_path),
        "checkpoint": str(checkpoint),
        "source": str(source),
        "candidate": candidate_index,
        "role": chosen_role,
        "to_timeline": bool(to_timeline),
        "start": media.start,
        "duration": media.duration,
        "score": media.score,
    }
