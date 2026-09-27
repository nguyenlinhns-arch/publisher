from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .analysis_frames import compose_contact_sheet, extract_candidate_frames
from .cache import prune_cache, source_signature
from .checkpoint import create_checkpoint
from .media import MediaAudit, audit_media_info, infer_role, probe
from .proxy import ensure_proxy
from .shot_detection import ShotSpan, detect_shots
from .planner import build_rough_cut
from .project import MediaItem, ProjectState
from .visual_metrics import analyze_frame, annotate_duplicate_groups

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
    technical_rank: int = 0
    fingerprint: str = ""
    duplicate_of: int | None = None
    global_duplicate_of: str = ""
    warnings: tuple[str, ...] = ()
    decision: str = "PENDING"
    review_role: str = ""
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
    analysis_source: str = ""
    proxy_reused: bool = False
    shot_count: int = 0
    selection_mode: str = "UNIFORM"
    visual_review: str = "PENDING"
    notes: str = (
        "Điểm kỹ thuật chỉ hỗ trợ sàng lọc. Rung, motion blur, crop mặt, "
        "hành động, cảm xúc và bố cục vẫn cần duyệt hình."
    )


def _safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-")
    try:
        digest = source_signature(path).key[:12]
    except Exception:
        digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
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


def candidates_from_shots(
    shots: tuple[ShotSpan, ...],
    *,
    count: int = 12,
    segment_seconds: float = 3.4,
) -> tuple[CandidateWindow, ...]:
    usable = [shot for shot in shots if shot.duration >= 0.45]
    if not usable:
        return ()

    count = max(1, min(24, int(count)))
    segment_seconds = max(0.5, float(segment_seconds))
    if len(usable) <= count:
        chosen = usable
    else:
        # Even coverage across the full story, not just the longest shots.
        positions = [
            round(index * (len(usable) - 1) / max(1, count - 1))
            for index in range(count)
        ]
        chosen = [usable[position] for position in positions]

    result: list[CandidateWindow] = []
    for index, shot in enumerate(chosen, start=1):
        duration = min(segment_seconds, shot.duration)
        center = (shot.start + shot.end) / 2
        start = max(shot.start, min(shot.end - duration, center - duration / 2))
        end = min(shot.end, start + duration)
        result.append(
            CandidateWindow(
                index=index,
                center=round((start + end) / 2, 3),
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
                fingerprint=metric.dhash,
                duplicate_of=duplicate_of,
                warnings=tuple(warnings),
            )
        )
    ranked = sorted(
        range(len(result)),
        key=lambda idx: result[idx].technical_score,
        reverse=True,
    )
    rank_by_index = {index: rank + 1 for rank, index in enumerate(ranked)}
    return tuple(
        replace(item, technical_rank=rank_by_index[index])
        for index, item in enumerate(result)
    )


def _annotate_global_duplicates(items: list[dict[str, Any]], *, threshold: int = 4) -> None:
    from .visual_metrics import hamming_distance

    previous: list[tuple[str, str]] = []
    for item_index, item in enumerate(items, start=1):
        candidates = item.get("candidates") or []
        for candidate_index, candidate in enumerate(candidates, start=1):
            fingerprint = str(candidate.get("fingerprint") or "")
            if not fingerprint:
                continue
            duplicate = ""
            for ref, old_fingerprint in previous:
                if hamming_distance(fingerprint, old_fingerprint) <= threshold:
                    duplicate = ref
                    break
            candidate["global_duplicate_of"] = duplicate
            previous.append((f"{item_index}:{candidate_index}", fingerprint))


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

    analysis_source = source
    proxy_reused = False
    proxy_warning = ""
    try:
        proxy = ensure_proxy(source)
        analysis_source = Path(proxy.proxy)
        proxy_reused = proxy.reused
    except Exception as exc:
        proxy_warning = f"proxy_fallback:{type(exc).__name__}"

    shots: tuple[ShotSpan, ...] = ()
    selection_mode = "UNIFORM"
    try:
        shots = detect_shots(analysis_source)
        base_candidates = candidates_from_shots(
            shots,
            count=tiles,
            segment_seconds=candidate_seconds,
        )
        if base_candidates:
            selection_mode = "SHOT_BOUNDARY"
        else:
            raise RuntimeError("no-shot-candidates")
    except Exception:
        base_candidates = candidate_windows(
            info.duration,
            count=tiles,
            segment_seconds=candidate_seconds,
        )

    frames = extract_candidate_frames(
        analysis_source,
        [candidate.center for candidate in base_candidates],
        target_dir / "candidates",
    )
    sheet = target_dir / "source_contact_sheet.jpg"
    compose_contact_sheet(
        frames,
        sheet,
        columns=columns,
    )
    candidates = _enrich_candidates(base_candidates, frames)

    audit_warnings = list(audit.warnings)
    if proxy_warning:
        audit_warnings.append(proxy_warning)

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
        audit_warnings=tuple(audit_warnings),
        candidates=candidates,
        analysis_source=str(analysis_source),
        proxy_reused=proxy_reused,
        shot_count=len(shots),
        selection_mode=selection_mode,
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
    item_payloads = [asdict(item) for item in items]
    _annotate_global_duplicates(item_payloads)
    _atomic_json_write(
        manifest,
        {
            "schema": REVIEW_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": item_payloads,
            "errors": errors,
            "policy": {
                "technical_audit": "AUTOMATED",
                "visual_metrics": "HEURISTIC_RANKING_ONLY",
                "technical_rank": "PER_SOURCE_NOT_AESTHETIC_RANK",
                "proxy_cache": "ENABLED",
                "shot_detection": "PREFERRED_WITH_UNIFORM_FALLBACK",
                "duplicate_detection": "PERCEPTUAL_HASH_HEURISTIC",
                "visual_quality": "PENDING_HUMAN_OR_VISION_REVIEW",
                "auto_accept_visual": False,
                "promotion_requires": "KEEP",
            },
        },
    )
    # Derived proxies/analysis files are disposable. Keep the cache bounded
    # without ever deleting original footage or project files.
    try:
        prune_cache()
    except Exception:
        pass
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
    role: str = "",
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
    if role.strip():
        candidate["review_role"] = role.strip()
    candidate["review_note"] = note.strip()
    candidate["status"] = (
        "VISUAL_REVIEWED"
        if decision != "PENDING"
        else "PENDING_VISUAL_REVIEW"
    )
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json_write(manifest, payload)
    return manifest


def apply_kept_candidates(
    manifest: Path,
    project_path: Path,
    *,
    build_timeline: bool = True,
) -> dict[str, Any]:
    manifest = manifest.expanduser().resolve()
    project_path = project_path.expanduser().resolve()
    payload = load_review_manifest(manifest)
    project = ProjectState.load(project_path)

    selected: list[MediaItem] = []
    skipped_rejected = 0
    missing_sources: list[str] = []

    for item in payload["items"]:
        if bool(item.get("audit_reject")):
            skipped_rejected += 1
            continue
        source = Path(str(item.get("source") or "")).expanduser().resolve()
        if not source.is_file():
            missing_sources.append(str(source))
            continue
        for candidate in item.get("candidates") or []:
            if str(candidate.get("decision") or "").upper() != "KEEP":
                continue
            role = str(candidate.get("review_role") or "").strip() or infer_role(source)
            keep_audio = project.profile == "TALKING_HEAD_EXPERT"
            selected.append(
                MediaItem(
                    path=str(source),
                    kind="video",
                    role=role or "detail",
                    start=float(candidate.get("start") or 0.0),
                    duration=float(candidate.get("duration") or 0.0),
                    score=max(
                        0.0,
                        min(
                            1.0,
                            float(
                                candidate.get("technical_score")
                                or item.get("audit_score")
                                or 0.5
                            ),
                        ),
                    ),
                    motion="none",
                    keep_audio=keep_audio,
                    source_gain=1.0 if keep_audio else 0.10,
                )
            )

    if not selected:
        raise ValueError("Chưa có candidate KEEP hợp lệ để tạo rough cut.")

    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-review-build",
    )

    existing_keys = {
        (item.path, round(item.start, 3), round(item.duration, 3))
        for item in project.media
    }
    added = 0
    for item in selected:
        key = (item.path, round(item.start, 3), round(item.duration, 3))
        if key not in existing_keys:
            project.media.append(MediaItem(**asdict(item)))
            existing_keys.add(key)
            added += 1

    if build_timeline:
        reviewed = deepcopy(project)
        reviewed.media = [MediaItem(**asdict(item)) for item in selected]
        timeline = build_rough_cut(reviewed)
        if not timeline:
            raise ValueError("Các candidate KEEP chưa đủ để tạo rough cut.")
        project.timeline = timeline

    project.dirty = True
    project.save(project_path)
    return {
        "status": "DONE",
        "project": str(project_path),
        "checkpoint": str(checkpoint),
        "keep_candidates": len(selected),
        "media_added": added,
        "timeline_scenes": len(project.timeline),
        "duration": round(sum(item.duration for item in project.timeline), 3),
        "missing_sources": missing_sources,
        "technical_reject_items": skipped_rejected,
    }


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
