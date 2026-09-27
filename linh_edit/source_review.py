from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .contact_sheet import extract_contact_sheet
from .media import MediaAudit, audit_media_info, probe

REVIEW_SCHEMA = "linh-edit.source-review.v1"


@dataclass(frozen=True, slots=True)
class CandidateWindow:
    index: int
    center: float
    start: float
    end: float
    duration: float
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
    notes: str = "Rung, motion blur, crop mặt, hành động và cảnh trùng cần duyệt bằng mắt."


def _safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-")
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"{stem[:70] or 'media'}-{digest}"


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

    # Keep review windows away from the first/last few frames, while sampling
    # the whole clip evenly. These are candidates only, never auto-approved.
    margin = min(segment_seconds / 2, duration * 0.08)
    left = margin
    right = max(left, duration - margin)
    effective = max(1, min(count, math.ceil(duration / max(segment_seconds, 1.0))))

    if effective == 1:
        centers = [duration / 2]
    else:
        centers = [
            left + (right - left) * index / (effective - 1)
            for index in range(effective)
        ]

    result: list[CandidateWindow] = []
    for index, center in enumerate(centers, start=1):
        start = max(0.0, min(duration - segment_seconds, center - segment_seconds / 2))
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
    candidates = candidate_windows(
        info.duration,
        count=tiles,
        segment_seconds=candidate_seconds,
    )

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
    item_manifest = target_dir / "review.json"
    item_manifest.write_text(
        json.dumps(
            {
                "schema": REVIEW_SCHEMA,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                **asdict(item),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
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
    manifest.write_text(
        json.dumps(
            {
                "schema": REVIEW_SCHEMA,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items": [asdict(item) for item in items],
                "errors": errors,
                "policy": {
                    "technical_audit": "AUTOMATED",
                    "visual_quality": "PENDING_HUMAN_OR_VISION_REVIEW",
                    "auto_accept_visual": False,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest
