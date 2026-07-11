"""Domain models for the local social publisher.

The database stores enum values as stable, lower-case strings.  Datetimes are
timezone-aware in Python and are normalised to UTC by the repository layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


class StrEnum(str, Enum):
    """A small Python 3.10-compatible equivalent of :class:`enum.StrEnum`."""

    def __str__(self) -> str:
        return self.value


class Platform(StrEnum):
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"


class PostStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    READY = "ready"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    COMPLETED = "completed"
    PARTIAL = "partial"
    NEEDS_ACTION = "needs_action"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    PREPARING = "preparing"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SCHEDULED = "scheduled"
    RETRY_WAIT = "retry_wait"
    PUBLISHED = "published"
    UNKNOWN = "unknown"
    NEEDS_ACTION = "needs_action"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


TERMINAL_DELIVERY_STATUSES = frozenset(
    {
        DeliveryStatus.PUBLISHED,
        DeliveryStatus.NEEDS_ACTION,
        DeliveryStatus.FAILED,
        DeliveryStatus.UNKNOWN,
        DeliveryStatus.CANCELLED,
    }
)


def normalise_hashtags(hashtags: str | Iterable[str] | None) -> tuple[str, ...]:
    """Return a deterministic hashtag tuple without silently changing wording.

    A string is split on whitespace, while an iterable keeps each non-empty
    item.  Duplicate tags are removed case-sensitively and order is preserved.
    Leading ``#`` characters are intentionally not added by the data layer.
    """

    if hashtags is None:
        return ()
    values = hashtags.split() if isinstance(hashtags, str) else hashtags
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip()
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return tuple(result)


def media_fingerprint(video_path: str, video_sha256: str | None = None) -> str:
    """Build a cheap, deterministic media identity for approval invalidation.

    The media validator should pass a full SHA-256 when it has one.  As a safe
    fallback, an existing file contributes its canonical path, size and
    nanosecond modification time so replacing the file invalidates approval.
    """

    path = Path(video_path).expanduser()
    digest = video_sha256.strip().lower() if video_sha256 else ""
    try:
        resolved = path.resolve(strict=True)
        stat = resolved.stat()
        return f"media:{digest}:{resolved}:{stat.st_size}:{stat.st_mtime_ns}"
    except (OSError, RuntimeError):
        return f"media:{digest}:{path.resolve(strict=False)}:missing"


def compute_content_hash(
    *,
    video_path: str,
    caption: str,
    hashtags: str | Iterable[str] | None = None,
    video_sha256: str | None = None,
) -> str:
    """Hash every user-visible/content-bearing field that approval covers."""

    payload = {
        "caption": caption,
        "hashtags": list(normalise_hashtags(hashtags)),
        "media": media_fingerprint(video_path, video_sha256),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def compute_delivery_idempotency_key(
    *,
    platform: Platform | str,
    account_id: str | None,
    video_sha256: str | None,
    caption: str,
    hashtags: str | Iterable[str] | None,
    scheduled_at: datetime,
) -> str:
    """Identify one intended remote delivery across different local posts.

    The key deliberately excludes local paths and post ids.  Two drafts that
    target the same account with the same media, text and UTC minute therefore
    collide before either can create remote work.
    """

    if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
        raise ValueError("scheduled_at must include a timezone")
    payload = {
        "account_id": (account_id or "").strip().casefold(),
        "caption": caption,
        "hashtags": list(normalise_hashtags(hashtags)),
        "platform": str(platform),
        "scheduled_at_utc": scheduled_at.astimezone(timezone.utc)
        .replace(second=0, microsecond=0)
        .isoformat(),
        "video_sha256": (video_sha256 or "").strip().lower(),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Post:
    id: str
    title: str
    video_path: str
    video_sha256: str | None
    caption: str
    hashtags: tuple[str, ...]
    content_hash: str
    approval_hash: str | None
    approved_at: datetime | None
    scheduled_at: datetime | None
    timezone: str
    status: PostStatus
    created_at: datetime
    updated_at: datetime

    @property
    def is_approved(self) -> bool:
        return bool(self.approval_hash) and self.approval_hash == self.content_hash


@dataclass(frozen=True, slots=True)
class Delivery:
    id: str
    post_id: str
    platform: Platform
    account_id: str | None
    idempotency_key: str | None
    status: DeliveryStatus
    remote_upload_id: str | None
    remote_post_id: str | None
    remote_url: str | None
    attempt_count: int
    next_attempt_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    published_at: datetime | None
    lease_owner: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_DELIVERY_STATUSES


@dataclass(frozen=True, slots=True)
class Attempt:
    id: int
    delivery_id: str
    attempt_no: int
    phase: str
    status: AttemptStatus
    started_at: datetime
    finished_at: datetime | None
    retryable: bool | None
    error_code: str | None
    error_message: str | None
    request_id: str | None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Setting:
    key: str
    value: Any
    updated_at: datetime


class RepositoryError(RuntimeError):
    """Base class for data-layer failures that are safe to show in the GUI."""


class NotFoundError(RepositoryError):
    pass


class ValidationError(RepositoryError):
    pass


class InvalidStateError(RepositoryError):
    pass


class LeaseConflictError(RepositoryError):
    pass
