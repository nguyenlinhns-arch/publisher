"""Transactional repository for posts, per-platform deliveries and attempts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .db import Database
from .models import (
    Attempt,
    AttemptStatus,
    Delivery,
    DeliveryStatus,
    InvalidStateError,
    LeaseConflictError,
    NotFoundError,
    Platform,
    Post,
    PostStatus,
    Setting,
    ValidationError,
    compute_content_hash,
    normalise_hashtags,
)


_UNSET = object()
_MISSING = object()
_ACTIVE_DELIVERY_STATUSES = (
    DeliveryStatus.PREPARING,
    DeliveryStatus.UPLOADING,
    DeliveryStatus.PROCESSING,
    DeliveryStatus.AWAITING_CONFIRMATION,
)
_CONTENT_EDIT_BLOCKERS = (
    DeliveryStatus.RETRY_WAIT,
    DeliveryStatus.FAILED,
    DeliveryStatus.PREPARING,
    DeliveryStatus.UPLOADING,
    DeliveryStatus.PROCESSING,
    DeliveryStatus.AWAITING_CONFIRMATION,
    DeliveryStatus.SCHEDULED,
    DeliveryStatus.PUBLISHED,
    DeliveryStatus.NEEDS_ACTION,
    DeliveryStatus.UNKNOWN,
)


def _as_utc(value: datetime, *, field_name: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


def _datetime_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat(timespec="microseconds")


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Value is not JSON serialisable: {exc}") from exc


def _json_load(value: str, *, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _platform(value: Platform | str) -> Platform:
    try:
        return value if isinstance(value, Platform) else Platform(str(value))
    except ValueError as exc:
        raise ValidationError(f"Unsupported platform: {value!r}") from exc


def _post_from_row(row: sqlite3.Row) -> Post:
    hashtags = _json_load(row["hashtags_json"], fallback=[])
    return Post(
        id=row["id"],
        title=row["title"],
        video_path=row["video_path"],
        video_sha256=row["video_sha256"],
        caption=row["caption"],
        hashtags=tuple(str(item) for item in hashtags),
        content_hash=row["content_hash"],
        approval_hash=row["approval_hash"],
        approved_at=_parse_datetime(row["approved_at"]),
        scheduled_at=_parse_datetime(row["scheduled_at"]),
        timezone=row["timezone"],
        status=PostStatus(row["status"]),
        created_at=_parse_datetime(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_datetime(row["updated_at"]),  # type: ignore[arg-type]
    )


def _delivery_from_row(row: sqlite3.Row) -> Delivery:
    return Delivery(
        id=row["id"],
        post_id=row["post_id"],
        platform=Platform(row["platform"]),
        account_id=row["account_id"],
        status=DeliveryStatus(row["status"]),
        remote_upload_id=row["remote_upload_id"],
        remote_post_id=row["remote_post_id"],
        remote_url=row["remote_url"],
        attempt_count=int(row["attempt_count"]),
        next_attempt_at=_parse_datetime(row["next_attempt_at"]),
        last_error_code=row["last_error_code"],
        last_error_message=row["last_error_message"],
        published_at=_parse_datetime(row["published_at"]),
        lease_owner=row["lease_owner"],
        lease_token=row["lease_token"],
        lease_expires_at=_parse_datetime(row["lease_expires_at"]),
        created_at=_parse_datetime(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_datetime(row["updated_at"]),  # type: ignore[arg-type]
    )


def _attempt_from_row(row: sqlite3.Row) -> Attempt:
    details = _json_load(row["details_json"], fallback={})
    if not isinstance(details, Mapping):
        details = {}
    retryable = row["retryable"]
    return Attempt(
        id=int(row["id"]),
        delivery_id=row["delivery_id"],
        attempt_no=int(row["attempt_no"]),
        phase=row["phase"],
        status=AttemptStatus(row["status"]),
        started_at=_parse_datetime(row["started_at"]),  # type: ignore[arg-type]
        finished_at=_parse_datetime(row["finished_at"]),
        retryable=None if retryable is None else bool(retryable),
        error_code=row["error_code"],
        error_message=row["error_message"],
        request_id=row["request_id"],
        details=details,
    )


class Repository:
    """The only code allowed to mutate publisher state.

    The constructor initialises the schema idempotently, which makes both the
    GUI and scheduled worker safe to start independently.
    """

    def __init__(self, database: Database | str | Path) -> None:
        self.db = database if isinstance(database, Database) else Database(database)
        self.db.initialize()

    # ------------------------------------------------------------------ posts
    def create_post(
        self,
        *,
        video_path: str,
        caption: str = "",
        hashtags: str | Iterable[str] | None = None,
        title: str = "",
        video_sha256: str | None = None,
        timezone_name: str = "Asia/Ho_Chi_Minh",
        post_id: str | None = None,
        now: datetime | None = None,
    ) -> Post:
        video_path = str(video_path).strip()
        if not video_path:
            raise ValidationError("video_path is required.")
        if not timezone_name.strip():
            raise ValidationError("timezone_name is required.")
        post_id = post_id or uuid4().hex
        if not post_id.strip():
            raise ValidationError("post_id cannot be empty.")
        tags = normalise_hashtags(hashtags)
        content_hash = compute_content_hash(
            video_path=video_path,
            video_sha256=video_sha256,
            caption=caption,
            hashtags=tags,
        )
        stamp = _as_utc(now or _now(), field_name="now")
        stamp_text = _datetime_text(stamp)
        with self.db.transaction(immediate=True) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO posts(
                        id, title, video_path, video_sha256, caption,
                        hashtags_json, content_hash, timezone, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post_id,
                        title,
                        video_path,
                        video_sha256,
                        caption,
                        _json_dump(list(tags)),
                        content_hash,
                        timezone_name,
                        PostStatus.DRAFT.value,
                        stamp_text,
                        stamp_text,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValidationError(f"Post id already exists: {post_id}") from exc
            row = self._require_post_row(conn, post_id)
        return _post_from_row(row)

    def get_post(self, post_id: str) -> Post:
        with self.db.connection() as conn:
            return _post_from_row(self._require_post_row(conn, post_id))

    def get_post_with_deliveries(self, post_id: str) -> tuple[Post, list[Delivery]]:
        with self.db.connection() as conn:
            post = _post_from_row(self._require_post_row(conn, post_id))
            rows = conn.execute(
                "SELECT * FROM deliveries WHERE post_id = ? ORDER BY platform",
                (post_id,),
            ).fetchall()
            return post, [_delivery_from_row(row) for row in rows]

    def list_posts(
        self,
        *,
        statuses: PostStatus | str | Iterable[PostStatus | str] | None = None,
        search: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Post]:
        if limit < 1 or limit > 1000:
            raise ValidationError("limit must be between 1 and 1000.")
        if offset < 0:
            raise ValidationError("offset cannot be negative.")
        clauses: list[str] = []
        params: list[Any] = []
        if statuses is not None:
            raw = (
                [statuses]
                if isinstance(statuses, (PostStatus, str))
                else list(statuses)
            )
            parsed: list[str] = []
            for status in raw:
                try:
                    parsed.append(PostStatus(str(status)).value)
                except ValueError as exc:
                    raise ValidationError(
                        f"Unsupported post status: {status!r}"
                    ) from exc
            if not parsed:
                return []
            clauses.append("status IN (" + ",".join("?" for _ in parsed) + ")")
            params.extend(parsed)
        if search and search.strip():
            clauses.append("(title LIKE ? OR caption LIKE ? OR video_path LIKE ?)")
            needle = f"%{search.strip()}%"
            params.extend((needle, needle, needle))
        query = "SELECT * FROM posts"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend((limit, offset))
        with self.db.connection() as conn:
            return [
                _post_from_row(row) for row in conn.execute(query, params).fetchall()
            ]

    def update_post(
        self,
        post_id: str,
        *,
        title: str | object = _UNSET,
        video_path: str | object = _UNSET,
        video_sha256: str | None | object = _UNSET,
        caption: str | object = _UNSET,
        hashtags: str | Iterable[str] | None | object = _UNSET,
        timezone_name: str | object = _UNSET,
        expected_updated_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Post:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            current = _post_from_row(self._require_post_row(conn, post_id))
            if expected_updated_at is not None and current.updated_at != _as_utc(
                expected_updated_at, field_name="expected_updated_at"
            ):
                raise InvalidStateError(
                    "This post changed in another window. Reload it before saving."
                )
            new_video_path = (
                current.video_path if video_path is _UNSET else str(video_path).strip()
            )
            if not new_video_path:
                raise ValidationError("video_path is required.")
            new_caption = current.caption if caption is _UNSET else str(caption)
            new_sha = current.video_sha256 if video_sha256 is _UNSET else video_sha256
            if new_sha is not None:
                new_sha = str(new_sha).strip() or None
            new_tags = (
                current.hashtags if hashtags is _UNSET else normalise_hashtags(hashtags)  # type: ignore[arg-type]
            )
            new_title = current.title if title is _UNSET else str(title)
            new_timezone = (
                current.timezone
                if timezone_name is _UNSET
                else str(timezone_name).strip()
            )
            if not new_timezone:
                raise ValidationError("timezone_name is required.")
            new_hash = compute_content_hash(
                video_path=new_video_path,
                video_sha256=new_sha,
                caption=new_caption,
                hashtags=new_tags,
            )
            content_changed = new_hash != current.content_hash
            if content_changed:
                blocker = conn.execute(
                    "SELECT platform, status FROM deliveries "
                    "WHERE post_id = ? AND status IN ("
                    + ",".join("?" for _ in _CONTENT_EDIT_BLOCKERS)
                    + ") LIMIT 1",
                    (post_id, *(status.value for status in _CONTENT_EDIT_BLOCKERS)),
                ).fetchone()
                if blocker:
                    raise InvalidStateError(
                        "Content cannot change while a delivery is active, published, "
                        f"or awaiting review ({blocker['platform']}: {blocker['status']})."
                    )
            status = PostStatus.DRAFT if content_changed else current.status
            approval_hash = None if content_changed else current.approval_hash
            approved_at = (
                None if content_changed else _datetime_text(current.approved_at)
            )
            scheduled_at = (
                None if content_changed else _datetime_text(current.scheduled_at)
            )
            conn.execute(
                """
                UPDATE posts SET
                    title = ?, video_path = ?, video_sha256 = ?, caption = ?,
                    hashtags_json = ?, content_hash = ?, approval_hash = ?,
                    approved_at = ?, scheduled_at = ?, timezone = ?, status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_title,
                    new_video_path,
                    new_sha,
                    new_caption,
                    _json_dump(list(new_tags)),
                    new_hash,
                    approval_hash,
                    approved_at,
                    scheduled_at,
                    new_timezone,
                    status.value,
                    _datetime_text(stamp),
                    post_id,
                ),
            )
            if content_changed:
                conn.execute(
                    """
                    UPDATE deliveries SET
                        next_attempt_at = NULL,
                        last_error_code = NULL,
                        last_error_message = NULL,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE post_id = ? AND status = 'pending'
                    """,
                    (_datetime_text(stamp), post_id),
                )
            row = self._require_post_row(conn, post_id)
        return _post_from_row(row)

    def delete_post(self, post_id: str) -> None:
        with self.db.transaction(immediate=True) as conn:
            self._require_post_row(conn, post_id)
            unsafe = conn.execute(
                """
                SELECT 1 FROM deliveries d
                WHERE d.post_id = ?
                  AND (
                    d.status IN (
                        'preparing', 'uploading', 'processing',
                        'awaiting_confirmation', 'scheduled', 'published',
                        'unknown', 'needs_action'
                    )
                    OR EXISTS (SELECT 1 FROM attempts a WHERE a.delivery_id = d.id)
                  )
                LIMIT 1
                """,
                (post_id,),
            ).fetchone()
            if unsafe:
                raise InvalidStateError(
                    "Posts with delivery history or an uncertain remote outcome "
                    "cannot be deleted. Cancel or archive them instead."
                )
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))

    def approve_post(self, post_id: str, *, now: datetime | None = None) -> Post:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            current = _post_from_row(self._require_post_row(conn, post_id))
            path = Path(current.video_path).expanduser()
            if not path.is_file():
                raise ValidationError(
                    "The video file does not exist; the post cannot be approved."
                )
            blocker = conn.execute(
                """
                SELECT platform, status FROM deliveries
                WHERE post_id = ? AND (
                    status IN (
                        'preparing', 'uploading', 'processing',
                        'awaiting_confirmation', 'scheduled', 'published',
                        'unknown', 'needs_action'
                    )
                    OR remote_upload_id IS NOT NULL
                    OR remote_post_id IS NOT NULL
                )
                LIMIT 1
                """,
                (post_id,),
            ).fetchone()
            if blocker:
                raise InvalidStateError(
                    "Approval cannot change after remote work has begun "
                    f"({blocker['platform']}: {blocker['status']})."
                )
            current_hash = compute_content_hash(
                video_path=current.video_path,
                video_sha256=current.video_sha256,
                caption=current.caption,
                hashtags=current.hashtags,
            )
            if current.is_approved and current_hash == current.content_hash:
                return current
            conn.execute(
                """
                UPDATE posts SET content_hash = ?, approval_hash = ?,
                    approved_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    current_hash,
                    current_hash,
                    _datetime_text(stamp),
                    _datetime_text(stamp),
                    post_id,
                ),
            )
            self._recalculate_post_status(conn, post_id, stamp)
            row = self._require_post_row(conn, post_id)
        return _post_from_row(row)

    def revoke_approval(self, post_id: str, *, now: datetime | None = None) -> Post:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            self._require_post_row(conn, post_id)
            active = conn.execute(
                "SELECT 1 FROM deliveries WHERE post_id = ? "
                "AND status IN ('retry_wait', 'failed', 'preparing', 'uploading', 'processing', "
                "'awaiting_confirmation', 'scheduled', 'published', 'unknown', "
                "'needs_action') "
                "LIMIT 1",
                (post_id,),
            ).fetchone()
            if active:
                raise InvalidStateError(
                    "Approval cannot be revoked after remote publishing has begun."
                )
            conn.execute(
                """
                UPDATE posts SET approval_hash = NULL, approved_at = NULL,
                    scheduled_at = NULL, status = 'draft', updated_at = ?
                WHERE id = ?
                """,
                (_datetime_text(stamp), post_id),
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'pending', next_attempt_at = NULL,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE post_id = ? AND status = 'pending'
                """,
                (_datetime_text(stamp), post_id),
            )
            row = self._require_post_row(conn, post_id)
        return _post_from_row(row)

    # ------------------------------------------------------------- destinations
    def ensure_delivery(
        self,
        post_id: str,
        platform: Platform | str,
        *,
        account_id: str | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        parsed = _platform(platform)
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            self._require_post_row(conn, post_id)
            existing = conn.execute(
                "SELECT * FROM deliveries WHERE post_id = ? AND platform = ?",
                (post_id, parsed.value),
            ).fetchone()
            if existing:
                delivery = _delivery_from_row(existing)
                if delivery.status is DeliveryStatus.CANCELLED and (
                    delivery.remote_upload_id
                    or delivery.remote_post_id
                    or delivery.remote_url
                    or self._delivery_has_history(conn, delivery.id)
                ):
                    raise InvalidStateError(
                        "A cancelled delivery with remote/audit history cannot be "
                        "reused. Resolve its outcome or create a new post."
                    )
                if account_id != delivery.account_id:
                    if delivery.status not in {
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRY_WAIT,
                        DeliveryStatus.FAILED,
                        DeliveryStatus.CANCELLED,
                    }:
                        raise InvalidStateError(
                            "The account cannot change after publishing has begun."
                        )
                    conn.execute(
                        "UPDATE deliveries SET account_id = ?, "
                        "status = CASE WHEN status = 'cancelled' THEN 'pending' "
                        "ELSE status END, updated_at = ? WHERE id = ?",
                        (account_id, _datetime_text(stamp), delivery.id),
                    )
                elif delivery.status is DeliveryStatus.CANCELLED:
                    conn.execute(
                        "UPDATE deliveries SET status = 'pending', updated_at = ? "
                        "WHERE id = ?",
                        (_datetime_text(stamp), delivery.id),
                    )
                self._recalculate_post_status(conn, post_id, stamp)
                row = conn.execute(
                    "SELECT * FROM deliveries WHERE id = ?", (delivery.id,)
                ).fetchone()
                return _delivery_from_row(row)
            delivery_id = uuid4().hex
            conn.execute(
                """
                INSERT INTO deliveries(
                    id, post_id, platform, account_id, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    delivery_id,
                    post_id,
                    parsed.value,
                    account_id,
                    _datetime_text(stamp),
                    _datetime_text(stamp),
                ),
            )
            self._recalculate_post_status(conn, post_id, stamp)
            row = conn.execute(
                "SELECT * FROM deliveries WHERE id = ?", (delivery_id,)
            ).fetchone()
        return _delivery_from_row(row)

    def set_destinations(
        self,
        post_id: str,
        destinations: Mapping[Platform | str, str | None] | Iterable[Platform | str],
        *,
        now: datetime | None = None,
    ) -> list[Delivery]:
        if isinstance(destinations, Mapping):
            desired = {_platform(key): value for key, value in destinations.items()}
        else:
            desired = {_platform(item): None for item in destinations}
        if not desired:
            raise ValidationError("At least one destination is required.")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            self._require_post_row(conn, post_id)
            rows = conn.execute(
                "SELECT * FROM deliveries WHERE post_id = ?", (post_id,)
            ).fetchall()
            existing = {Platform(row["platform"]): row for row in rows}
            for platform, row in existing.items():
                if platform in desired:
                    continue
                delivery = _delivery_from_row(row)
                if delivery.lease_token:
                    raise InvalidStateError(
                        f"Cannot remove {platform.value} while a worker owns it."
                    )
                if delivery.status not in {
                    DeliveryStatus.PENDING,
                    DeliveryStatus.RETRY_WAIT,
                    DeliveryStatus.FAILED,
                    DeliveryStatus.CANCELLED,
                }:
                    raise InvalidStateError(
                        f"Cannot remove {platform.value} after publishing has begun."
                    )
                has_attempt = conn.execute(
                    "SELECT 1 FROM attempts WHERE delivery_id = ? LIMIT 1",
                    (delivery.id,),
                ).fetchone()
                if has_attempt:
                    conn.execute(
                        """
                        UPDATE deliveries SET status = 'cancelled',
                            next_attempt_at = NULL, lease_owner = NULL,
                            lease_token = NULL, lease_expires_at = NULL,
                            updated_at = ? WHERE id = ?
                        """,
                        (_datetime_text(stamp), delivery.id),
                    )
                else:
                    conn.execute("DELETE FROM deliveries WHERE id = ?", (delivery.id,))
            for platform, account_id in desired.items():
                row = existing.get(platform)
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO deliveries(
                            id, post_id, platform, account_id, status,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                        """,
                        (
                            uuid4().hex,
                            post_id,
                            platform.value,
                            account_id,
                            _datetime_text(stamp),
                            _datetime_text(stamp),
                        ),
                    )
                else:
                    delivery = _delivery_from_row(row)
                    if delivery.status is DeliveryStatus.CANCELLED and (
                        delivery.remote_upload_id
                        or delivery.remote_post_id
                        or delivery.remote_url
                        or self._delivery_has_history(conn, delivery.id)
                    ):
                        raise InvalidStateError(
                            f"Cancelled {platform.value} history cannot be reused."
                        )
                    if account_id != delivery.account_id and delivery.status not in {
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRY_WAIT,
                        DeliveryStatus.FAILED,
                        DeliveryStatus.CANCELLED,
                    }:
                        raise InvalidStateError(
                            f"Cannot change the {platform.value} account now."
                        )
                    conn.execute(
                        "UPDATE deliveries SET account_id = ?, "
                        "status = CASE WHEN status = 'cancelled' THEN 'pending' "
                        "ELSE status END, updated_at = ? WHERE id = ?",
                        (account_id, _datetime_text(stamp), delivery.id),
                    )
            self._recalculate_post_status(conn, post_id, stamp)
            final_rows = conn.execute(
                "SELECT * FROM deliveries WHERE post_id = ? ORDER BY platform",
                (post_id,),
            ).fetchall()
        return [_delivery_from_row(row) for row in final_rows]

    def get_delivery(self, delivery_id: str) -> Delivery:
        with self.db.connection() as conn:
            return _delivery_from_row(self._require_delivery_row(conn, delivery_id))

    def get_delivery_for_platform(
        self, post_id: str, platform: Platform | str
    ) -> Delivery:
        parsed = _platform(platform)
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM deliveries WHERE post_id = ? AND platform = ?",
                (post_id, parsed.value),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    f"No {parsed.value} delivery exists for post {post_id}."
                )
            return _delivery_from_row(row)

    def list_deliveries(
        self,
        *,
        post_id: str | None = None,
        statuses: DeliveryStatus | str | Iterable[DeliveryStatus | str] | None = None,
        limit: int = 1000,
    ) -> list[Delivery]:
        if limit < 1 or limit > 5000:
            raise ValidationError("limit must be between 1 and 5000.")
        clauses: list[str] = []
        params: list[Any] = []
        if post_id is not None:
            clauses.append("post_id = ?")
            params.append(post_id)
        if statuses is not None:
            raw = (
                [statuses]
                if isinstance(statuses, (DeliveryStatus, str))
                else list(statuses)
            )
            parsed: list[str] = []
            for status in raw:
                try:
                    parsed.append(DeliveryStatus(str(status)).value)
                except ValueError as exc:
                    raise ValidationError(
                        f"Unsupported delivery status: {status!r}"
                    ) from exc
            if not parsed:
                return []
            clauses.append("status IN (" + ",".join("?" for _ in parsed) + ")")
            params.extend(parsed)
        query = "SELECT * FROM deliveries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, platform LIMIT ?"
        params.append(limit)
        with self.db.connection() as conn:
            return [
                _delivery_from_row(row)
                for row in conn.execute(query, params).fetchall()
            ]

    # --------------------------------------------------------------- scheduling
    def schedule_post(
        self,
        post_id: str,
        scheduled_at: datetime,
        *,
        destinations: Mapping[Platform | str, str | None]
        | Iterable[Platform | str]
        | None = None,
        now: datetime | None = None,
    ) -> Post:
        due = _as_utc(scheduled_at, field_name="scheduled_at")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            post = _post_from_row(self._require_post_row(conn, post_id))
            self._assert_current_approval(conn, post, stamp)
            if destinations is not None:
                self._set_destinations_locked(conn, post_id, destinations, stamp)
            rows = conn.execute(
                "SELECT * FROM deliveries WHERE post_id = ? AND status != 'cancelled'",
                (post_id,),
            ).fetchall()
            if not rows:
                raise ValidationError("At least one destination is required.")
            for row in rows:
                delivery = _delivery_from_row(row)
                if delivery.status in {
                    DeliveryStatus.FAILED,
                    DeliveryStatus.RETRY_WAIT,
                }:
                    raise InvalidStateError(
                        f"{delivery.platform.value} is {delivery.status.value}; "
                        "explicitly requeue it after checking that no remote post "
                        "exists before scheduling again."
                    )
                if delivery.status is DeliveryStatus.PENDING and (
                    delivery.remote_upload_id
                    or delivery.remote_post_id
                    or delivery.remote_url
                ):
                    raise InvalidStateError(
                        f"Pending {delivery.platform.value} contains remote evidence; "
                        "resolve its outcome instead of scheduling it again."
                    )
                if delivery.status in {
                    DeliveryStatus.PREPARING,
                    DeliveryStatus.UPLOADING,
                    DeliveryStatus.PROCESSING,
                    DeliveryStatus.AWAITING_CONFIRMATION,
                    DeliveryStatus.SCHEDULED,
                    DeliveryStatus.PUBLISHED,
                    DeliveryStatus.UNKNOWN,
                    DeliveryStatus.NEEDS_ACTION,
                }:
                    raise InvalidStateError(
                        f"Cannot schedule while {delivery.platform.value} is "
                        f"{delivery.status.value}."
                    )
            conn.execute(
                """
                UPDATE posts SET scheduled_at = ?, status = 'scheduled',
                    updated_at = ? WHERE id = ?
                """,
                (_datetime_text(due), _datetime_text(stamp), post_id),
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'pending', next_attempt_at = ?,
                    last_error_code = NULL, last_error_message = NULL,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE post_id = ? AND status = 'pending'
                """,
                (_datetime_text(due), _datetime_text(stamp), post_id),
            )
            row = self._require_post_row(conn, post_id)
        return _post_from_row(row)

    def cancel_schedule(self, post_id: str, *, now: datetime | None = None) -> Post:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            post = _post_from_row(self._require_post_row(conn, post_id))
            requires_requeue = conn.execute(
                "SELECT platform, status FROM deliveries WHERE post_id = ? "
                "AND status IN ('retry_wait', 'failed') LIMIT 1",
                (post_id,),
            ).fetchone()
            if requires_requeue:
                raise InvalidStateError(
                    f"{requires_requeue['platform']} is "
                    f"{requires_requeue['status']}; explicitly requeue it before "
                    "cancelling or replacing the schedule."
                )
            active = conn.execute(
                "SELECT 1 FROM deliveries WHERE post_id = ? "
                "AND status IN ('preparing', 'uploading', 'processing', "
                "'awaiting_confirmation', 'scheduled', 'published', 'unknown', "
                "'needs_action') "
                "LIMIT 1",
                (post_id,),
            ).fetchone()
            if active:
                raise InvalidStateError(
                    "The schedule cannot be cancelled after remote publishing begins."
                )
            has_destination = conn.execute(
                "SELECT 1 FROM deliveries WHERE post_id = ? "
                "AND status != 'cancelled' LIMIT 1",
                (post_id,),
            ).fetchone()
            status = (
                PostStatus.READY
                if post.is_approved and has_destination
                else PostStatus.APPROVED
                if post.is_approved
                else PostStatus.DRAFT
            )
            conn.execute(
                "UPDATE posts SET scheduled_at = NULL, status = ?, updated_at = ? "
                "WHERE id = ?",
                (status.value, _datetime_text(stamp), post_id),
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'pending', next_attempt_at = NULL,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE post_id = ? AND status = 'pending'
                """,
                (_datetime_text(stamp), post_id),
            )
            row = self._require_post_row(conn, post_id)
        return _post_from_row(row)

    # ------------------------------------------------------------- worker lease
    def claim_delivery(
        self,
        delivery_id: str,
        worker_id: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> Delivery:
        """Claim a known delivery, including preparation before publish time."""

        worker_id = worker_id.strip()
        if not worker_id:
            raise ValidationError("worker_id is required.")
        if lease_seconds < 10 or lease_seconds > 3600:
            raise ValidationError("lease_seconds must be between 10 and 3600.")
        stamp = _as_utc(now or _now(), field_name="now")
        expiry = stamp + timedelta(seconds=lease_seconds)
        with self.db.transaction(immediate=True) as conn:
            delivery = _delivery_from_row(self._require_delivery_row(conn, delivery_id))
            if delivery.status not in {
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
                DeliveryStatus.AWAITING_CONFIRMATION,
                DeliveryStatus.SCHEDULED,
                DeliveryStatus.PROCESSING,
            }:
                raise InvalidStateError(
                    f"A delivery in state {delivery.status.value} cannot be claimed."
                )
            if delivery.lease_expires_at and delivery.lease_expires_at > stamp:
                raise LeaseConflictError("This delivery is already claimed.")
            post = _post_from_row(self._require_post_row(conn, delivery.post_id))
            if delivery.status in {
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
            }:
                if (
                    delivery.remote_upload_id
                    or delivery.remote_post_id
                    or delivery.remote_url
                ):
                    raise InvalidStateError(
                        "A pending/retry delivery with remote evidence cannot be "
                        "claimed for another mutation. Resolve or verify it instead."
                    )
                self._assert_current_approval(conn, post, stamp)
            elif not post.is_approved:
                raise InvalidStateError(
                    "The post approval was revoked after remote preparation."
                )
            token = uuid4().hex
            changed = conn.execute(
                """
                UPDATE deliveries SET lease_owner = ?, lease_token = ?,
                    lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                """,
                (
                    worker_id,
                    token,
                    _datetime_text(expiry),
                    _datetime_text(stamp),
                    delivery_id,
                    _datetime_text(stamp),
                ),
            ).rowcount
            if changed != 1:
                raise LeaseConflictError("This delivery was claimed by another worker.")
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def claim_due_delivery(
        self,
        worker_id: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
        platforms: Iterable[Platform | str] | None = None,
    ) -> Delivery | None:
        worker_id = worker_id.strip()
        if not worker_id:
            raise ValidationError("worker_id is required.")
        if lease_seconds < 10 or lease_seconds > 3600:
            raise ValidationError("lease_seconds must be between 10 and 3600.")
        stamp = _as_utc(now or _now(), field_name="now")
        expiry = stamp + timedelta(seconds=lease_seconds)
        parsed_platforms = None
        if platforms is not None:
            parsed_platforms = [_platform(item).value for item in platforms]
            if not parsed_platforms:
                return None
        with self.db.transaction(immediate=True) as conn:
            for _ in range(100):
                clauses = [
                    "(d.status IN ('awaiting_confirmation', 'scheduled', 'processing') "
                    "OR (d.status = 'retry_wait' AND "
                    "(d.remote_upload_id IS NOT NULL OR d.remote_post_id IS NOT NULL)))",
                    "(d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)",
                    "(d.lease_expires_at IS NULL OR d.lease_expires_at <= ?)",
                    "p.scheduled_at IS NOT NULL",
                    "p.approval_hash IS NOT NULL",
                    "p.approval_hash = p.content_hash",
                ]
                params: list[Any] = [
                    _datetime_text(stamp),
                    _datetime_text(stamp),
                ]
                if parsed_platforms is not None:
                    clauses.append(
                        "d.platform IN ("
                        + ",".join("?" for _ in parsed_platforms)
                        + ")"
                    )
                    params.extend(parsed_platforms)
                row = conn.execute(
                    """
                    SELECT d.*
                    FROM deliveries d
                    JOIN posts p ON p.id = d.post_id
                    WHERE """
                    + " AND ".join(clauses)
                    + " ORDER BY p.scheduled_at, d.created_at, d.platform LIMIT 1",
                    params,
                ).fetchone()
                if row is None:
                    return None
                lease_token = uuid4().hex
                changed = conn.execute(
                    """
                    UPDATE deliveries SET lease_owner = ?, lease_token = ?,
                        lease_expires_at = ?, updated_at = ?
                    WHERE id = ?
                      AND (
                        status IN ('awaiting_confirmation', 'scheduled', 'processing')
                        OR (status = 'retry_wait' AND
                            (remote_upload_id IS NOT NULL OR remote_post_id IS NOT NULL))
                      )
                      AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                    """,
                    (
                        worker_id,
                        lease_token,
                        _datetime_text(expiry),
                        _datetime_text(stamp),
                        row["id"],
                        _datetime_text(stamp),
                    ),
                ).rowcount
                if changed == 1:
                    claimed = self._require_delivery_row(conn, row["id"])
                    return _delivery_from_row(claimed)
            return None

    def renew_lease(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> Delivery:
        if lease_seconds < 10 or lease_seconds > 3600:
            raise ValidationError("lease_seconds must be between 10 and 3600.")
        stamp = _as_utc(now or _now(), field_name="now")
        expiry = stamp + timedelta(seconds=lease_seconds)
        with self.db.transaction(immediate=True) as conn:
            self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            conn.execute(
                "UPDATE deliveries SET lease_expires_at = ?, updated_at = ? "
                "WHERE id = ? AND lease_token = ?",
                (
                    _datetime_text(expiry),
                    _datetime_text(stamp),
                    delivery_id,
                    lease_token,
                ),
            )
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def release_lease(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        now: datetime | None = None,
    ) -> Delivery:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in {
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
            }:
                raise InvalidStateError(
                    "An active remote operation cannot be released; record its "
                    "result or mark it as needs_action."
                )
            conn.execute(
                """
                UPDATE deliveries SET lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ? WHERE id = ?
                """,
                (_datetime_text(stamp), delivery_id),
            )
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def recover_expired_leases(self, *, now: datetime | None = None) -> int:
        """Recover abandoned work without ever blindly retrying an upload.

        A lease abandoned before ``uploading`` is safe to release.  Once a
        remote request may have begun, the outcome is ambiguous and requires a
        human check, preventing duplicate posts after a worker crash.
        """

        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            rows = conn.execute(
                "SELECT * FROM deliveries WHERE lease_expires_at IS NOT NULL "
                "AND lease_expires_at <= ?",
                (_datetime_text(stamp),),
            ).fetchall()
            affected_posts: set[str] = set()
            for row in rows:
                delivery = _delivery_from_row(row)
                affected_posts.add(delivery.post_id)
                if delivery.status in {
                    DeliveryStatus.PENDING,
                    DeliveryStatus.RETRY_WAIT,
                    DeliveryStatus.AWAITING_CONFIRMATION,
                    DeliveryStatus.SCHEDULED,
                    DeliveryStatus.PROCESSING,
                }:
                    conn.execute(
                        """
                        UPDATE deliveries SET lease_owner = NULL,
                            lease_token = NULL, lease_expires_at = NULL,
                            updated_at = ? WHERE id = ?
                        """,
                        (_datetime_text(stamp), delivery.id),
                    )
                    continue
                conn.execute(
                    """
                    UPDATE deliveries SET status = 'needs_action',
                        last_error_code = 'lease_expired_unknown_outcome',
                        last_error_message = ?, next_attempt_at = NULL,
                        lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, updated_at = ? WHERE id = ?
                    """,
                    (
                        "Worker stopped after remote publishing may have begun; "
                        "check the platform before retrying.",
                        _datetime_text(stamp),
                        delivery.id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE attempts SET status = 'unknown', finished_at = ?,
                        retryable = 0,
                        error_code = 'lease_expired_unknown_outcome',
                        error_message = ?
                    WHERE delivery_id = ? AND status = 'started'
                    """,
                    (
                        _datetime_text(stamp),
                        "Worker lease expired before the remote outcome was saved.",
                        delivery.id,
                    ),
                )
            for post_id in affected_posts:
                self._recalculate_post_status(conn, post_id, stamp)
            return len(rows)

    # ------------------------------------------------------- delivery transitions
    def checkpoint_remote_id(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_upload_id: str | None = None,
        remote_post_id: str | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        """Persist the first remote identifiers before the next network call.

        The lease deliberately remains owned by the caller.  Existing IDs can
        never be silently replaced because that could detach an audit trail
        from a real remote post.
        """

        upload_id = remote_upload_id.strip() if remote_upload_id else None
        post_id = remote_post_id.strip() if remote_post_id else None
        if not upload_id and not post_id:
            raise ValidationError("At least one remote identifier is required.")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            self._assert_remote_ids_compatible(
                delivery,
                remote_upload_id=upload_id,
                remote_post_id=post_id,
            )
            conn.execute(
                """
                UPDATE deliveries SET
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    remote_post_id = COALESCE(remote_post_id, ?),
                    updated_at = ?
                WHERE id = ? AND lease_token = ?
                """,
                (
                    upload_id,
                    post_id,
                    _datetime_text(stamp),
                    delivery_id,
                    lease_token,
                ),
            )
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_preparing(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        now: datetime | None = None,
    ) -> Delivery:
        return self._leased_transition(
            delivery_id,
            lease_token,
            allowed={DeliveryStatus.PENDING, DeliveryStatus.RETRY_WAIT},
            new_status=DeliveryStatus.PREPARING,
            now=now,
            remote_upload_id=None,
        )

    def mark_uploading(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_upload_id: str | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        return self._leased_transition(
            delivery_id,
            lease_token,
            allowed={
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
                DeliveryStatus.PREPARING,
            },
            new_status=DeliveryStatus.UPLOADING,
            now=now,
            remote_upload_id=remote_upload_id,
        )

    def mark_processing(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_upload_id: str | None = None,
        next_check_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        stamp = _as_utc(now or _now(), field_name="now")
        check_at = _as_utc(next_check_at or stamp, field_name="next_check_at")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in {
                DeliveryStatus.PREPARING,
                DeliveryStatus.UPLOADING,
                DeliveryStatus.PROCESSING,
                DeliveryStatus.AWAITING_CONFIRMATION,
                DeliveryStatus.SCHEDULED,
            }:
                raise InvalidStateError(
                    f"Cannot mark {delivery.status.value} as processing."
                )
            self._assert_remote_ids_compatible(
                delivery, remote_upload_id=remote_upload_id
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'processing',
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    next_attempt_at = ?, last_error_code = NULL,
                    last_error_message = NULL, lease_owner = NULL,
                    lease_token = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    remote_upload_id,
                    _datetime_text(check_at),
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_awaiting_confirmation(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_upload_id: str | None = None,
        next_check_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        stamp = _as_utc(now or _now(), field_name="now")
        check_at = _as_utc(next_check_at or stamp, field_name="next_check_at")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in {
                DeliveryStatus.PREPARING,
                DeliveryStatus.UPLOADING,
                DeliveryStatus.PROCESSING,
                DeliveryStatus.AWAITING_CONFIRMATION,
            }:
                raise InvalidStateError(
                    f"Cannot request confirmation from {delivery.status.value}."
                )
            self._assert_remote_ids_compatible(
                delivery, remote_upload_id=remote_upload_id
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'awaiting_confirmation',
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    next_attempt_at = ?, last_error_code = NULL,
                    last_error_message = NULL, lease_owner = NULL,
                    lease_token = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    remote_upload_id,
                    _datetime_text(check_at),
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_scheduled(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_post_id: str | None = None,
        remote_upload_id: str | None = None,
        remote_url: str | None = None,
        next_check_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        """Record that the platform accepted a future publish operation."""

        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in {
                DeliveryStatus.PREPARING,
                DeliveryStatus.UPLOADING,
                DeliveryStatus.PROCESSING,
                DeliveryStatus.AWAITING_CONFIRMATION,
                DeliveryStatus.SCHEDULED,
            }:
                raise InvalidStateError(
                    f"Cannot mark {delivery.status.value} as scheduled."
                )
            self._assert_remote_ids_compatible(
                delivery,
                remote_upload_id=remote_upload_id,
                remote_post_id=remote_post_id,
            )
            post = _post_from_row(self._require_post_row(conn, delivery.post_id))
            check_at = next_check_at or post.scheduled_at or stamp
            check_at = _as_utc(check_at, field_name="next_check_at")
            conn.execute(
                """
                UPDATE deliveries SET status = 'scheduled',
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    remote_post_id = COALESCE(remote_post_id, ?),
                    remote_url = COALESCE(?, remote_url), next_attempt_at = ?,
                    last_error_code = NULL, last_error_message = NULL,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ? WHERE id = ?
                """,
                (
                    remote_upload_id,
                    remote_post_id,
                    remote_url,
                    _datetime_text(check_at),
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_unknown(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_upload_id: str | None = None,
        remote_post_id: str | None = None,
        error_code: str = "unknown_remote_outcome",
        error_message: str = "Check the platform before retrying.",
        now: datetime | None = None,
    ) -> Delivery:
        remote_upload_id = (
            remote_upload_id.strip() if remote_upload_id else None
        ) or None
        remote_post_id = (remote_post_id.strip() if remote_post_id else None) or None
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status in {
                DeliveryStatus.PUBLISHED,
                DeliveryStatus.CANCELLED,
            }:
                raise InvalidStateError(
                    f"Cannot mark {delivery.status.value} as unknown."
                )
            self._assert_remote_ids_compatible(
                delivery,
                remote_upload_id=remote_upload_id,
                remote_post_id=remote_post_id,
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'unknown', next_attempt_at = NULL,
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    remote_post_id = COALESCE(remote_post_id, ?),
                    last_error_code = ?, last_error_message = ?,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ? WHERE id = ?
                """,
                (
                    remote_upload_id,
                    remote_post_id,
                    error_code,
                    error_message,
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def resolve_as_published(
        self,
        delivery_id: str,
        *,
        remote_post_id: str,
        url: str | None = None,
        confirmed_by: str,
        now: datetime | None = None,
    ) -> Delivery:
        """Resolve an uncertain delivery from platform evidence, without a lease."""

        remote_post_id = remote_post_id.strip()
        confirmed_by = confirmed_by.strip()
        if not remote_post_id:
            raise ValidationError("remote_post_id is required.")
        if not confirmed_by:
            raise ValidationError("confirmed_by is required for the audit trail.")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = _delivery_from_row(self._require_delivery_row(conn, delivery_id))
            self._assert_remote_ids_compatible(delivery, remote_post_id=remote_post_id)
            if delivery.status is DeliveryStatus.PUBLISHED:
                if url and not delivery.remote_url:
                    conn.execute(
                        "UPDATE deliveries SET remote_url = ?, updated_at = ? "
                        "WHERE id = ?",
                        (url, _datetime_text(stamp), delivery_id),
                    )
                    return _delivery_from_row(
                        self._require_delivery_row(conn, delivery_id)
                    )
                return delivery

            max_row = conn.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) AS n FROM attempts "
                "WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
            attempt_no = max(delivery.attempt_count, int(max_row["n"])) + 1
            conn.execute(
                """
                UPDATE attempts SET status = 'unknown', finished_at = ?,
                    retryable = 0, error_code = 'manually_resolved',
                    error_message = 'Superseded by manual platform verification.'
                WHERE delivery_id = ? AND status = 'started'
                """,
                (_datetime_text(stamp), delivery_id),
            )
            conn.execute(
                """
                INSERT INTO attempts(
                    delivery_id, attempt_no, phase, status, started_at,
                    finished_at, retryable, details_json
                ) VALUES (?, ?, 'manual_resolution', 'succeeded', ?, ?, 0, ?)
                """,
                (
                    delivery_id,
                    attempt_no,
                    _datetime_text(stamp),
                    _datetime_text(stamp),
                    _json_dump(
                        {
                            "confirmed_by": confirmed_by,
                            "previous_status": delivery.status.value,
                            "remote_post_id": remote_post_id,
                            "remote_url": url,
                        }
                    ),
                ),
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'published',
                    remote_post_id = COALESCE(remote_post_id, ?),
                    remote_url = COALESCE(?, remote_url), published_at = ?,
                    attempt_count = ?, next_attempt_at = NULL,
                    last_error_code = NULL, last_error_message = NULL,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ? WHERE id = ?
                """,
                (
                    remote_post_id,
                    url,
                    _datetime_text(stamp),
                    attempt_no,
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_published(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        remote_post_id: str,
        remote_url: str | None = None,
        remote_upload_id: str | None = None,
        published_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        if not remote_post_id.strip():
            raise ValidationError("remote_post_id is required for a published post.")
        stamp = _as_utc(now or _now(), field_name="now")
        published = _as_utc(published_at or stamp, field_name="published_at")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in {
                DeliveryStatus.PREPARING,
                DeliveryStatus.UPLOADING,
                DeliveryStatus.PROCESSING,
                DeliveryStatus.AWAITING_CONFIRMATION,
                DeliveryStatus.SCHEDULED,
            }:
                raise InvalidStateError(
                    f"Cannot publish a delivery in state {delivery.status.value}."
                )
            self._assert_remote_ids_compatible(
                delivery,
                remote_upload_id=remote_upload_id,
                remote_post_id=remote_post_id,
            )
            conn.execute(
                """
                UPDATE deliveries SET status = 'published',
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    remote_post_id = COALESCE(remote_post_id, ?),
                    remote_url = COALESCE(?, remote_url), published_at = ?,
                    next_attempt_at = NULL, last_error_code = NULL,
                    last_error_message = NULL, lease_owner = NULL,
                    lease_token = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    remote_upload_id,
                    remote_post_id,
                    remote_url,
                    _datetime_text(published),
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_retry_wait(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        next_attempt_at: datetime,
        error_code: str,
        error_message: str,
        now: datetime | None = None,
    ) -> Delivery:
        retry_at = _as_utc(next_attempt_at, field_name="next_attempt_at")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in {
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
                DeliveryStatus.UPLOADING,
                DeliveryStatus.PROCESSING,
                DeliveryStatus.SCHEDULED,
            }:
                raise InvalidStateError(
                    f"Cannot retry a delivery in state {delivery.status.value}."
                )
            conn.execute(
                """
                UPDATE deliveries SET status = 'retry_wait', next_attempt_at = ?,
                    last_error_code = ?, last_error_message = ?,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ? WHERE id = ?
                """,
                (
                    _datetime_text(retry_at),
                    error_code,
                    error_message,
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def mark_failed(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        error_code: str,
        error_message: str,
        now: datetime | None = None,
    ) -> Delivery:
        return self._mark_terminal_error(
            delivery_id,
            lease_token,
            status=DeliveryStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            remote_upload_id=None,
            remote_post_id=None,
            now=now,
        )

    def mark_needs_action(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        error_code: str,
        error_message: str,
        remote_upload_id: str | None = None,
        remote_post_id: str | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        remote_upload_id = (
            remote_upload_id.strip() if remote_upload_id else None
        ) or None
        remote_post_id = (remote_post_id.strip() if remote_post_id else None) or None
        return self._mark_terminal_error(
            delivery_id,
            lease_token,
            status=DeliveryStatus.NEEDS_ACTION,
            error_code=error_code,
            error_message=error_message,
            remote_upload_id=remote_upload_id,
            remote_post_id=remote_post_id,
            now=now,
        )

    def requeue_delivery(
        self,
        delivery_id: str,
        *,
        confirmed_no_remote: bool = False,
        next_attempt_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Delivery:
        """Explicit GUI action after a human confirms no remote post exists."""

        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = _delivery_from_row(self._require_delivery_row(conn, delivery_id))
            if delivery.status not in {
                DeliveryStatus.RETRY_WAIT,
                DeliveryStatus.FAILED,
                DeliveryStatus.NEEDS_ACTION,
                DeliveryStatus.UNKNOWN,
                DeliveryStatus.CANCELLED,
            }:
                raise InvalidStateError(
                    f"Cannot requeue a delivery in state {delivery.status.value}."
                )
            if (
                delivery.remote_upload_id
                or delivery.remote_post_id
                or delivery.remote_url
            ):
                raise InvalidStateError(
                    "A remote identifier already exists; this delivery must be "
                    "resolved, never requeued."
                )
            if (
                self._delivery_has_history(conn, delivery.id)
                and not confirmed_no_remote
            ):
                raise InvalidStateError(
                    "Delivery history exists. Confirm that no remote post exists "
                    "before requeueing."
                )
            post = _post_from_row(self._require_post_row(conn, delivery.post_id))
            self._assert_current_approval(conn, post, stamp)
            if post.scheduled_at is None:
                raise InvalidStateError("The post must be scheduled before requeueing.")
            due = next_attempt_at or stamp
            due = _as_utc(due, field_name="next_attempt_at")
            conn.execute(
                """
                UPDATE deliveries SET status = 'pending', next_attempt_at = ?,
                    last_error_code = NULL, last_error_message = NULL,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_datetime_text(due), _datetime_text(stamp), delivery_id),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    # --------------------------------------------------------------- attempts
    def begin_attempt(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        phase: str = "publish",
        request_id: str | None = None,
        details: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Attempt:
        if not phase.strip():
            raise ValidationError("phase is required.")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            row = self._require_delivery_row(conn, delivery_id)
            attempt_no = int(row["attempt_count"]) + 1
            cursor = conn.execute(
                """
                INSERT INTO attempts(
                    delivery_id, attempt_no, phase, status, started_at,
                    request_id, details_json
                ) VALUES (?, ?, ?, 'started', ?, ?, ?)
                """,
                (
                    delivery_id,
                    attempt_no,
                    phase,
                    _datetime_text(stamp),
                    request_id,
                    _json_dump(dict(details or {})),
                ),
            )
            conn.execute(
                "UPDATE deliveries SET attempt_count = ?, updated_at = ? WHERE id = ?",
                (attempt_no, _datetime_text(stamp), delivery_id),
            )
            attempt_row = conn.execute(
                "SELECT * FROM attempts WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return _attempt_from_row(attempt_row)

    def finish_attempt(
        self,
        attempt_id: int,
        status: AttemptStatus | str,
        *,
        retryable: bool | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        request_id: str | None = None,
        details: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Attempt:
        try:
            parsed = (
                status if isinstance(status, AttemptStatus) else AttemptStatus(status)
            )
        except ValueError as exc:
            raise ValidationError(f"Unsupported attempt status: {status!r}") from exc
        if parsed is AttemptStatus.STARTED:
            raise ValidationError("finish_attempt requires a terminal status.")
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            current = conn.execute(
                "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            if current is None:
                raise NotFoundError(f"Attempt not found: {attempt_id}")
            if AttemptStatus(current["status"]) is not AttemptStatus.STARTED:
                raise InvalidStateError("This attempt is already finished.")
            details_json = (
                current["details_json"]
                if details is None
                else _json_dump(dict(details))
            )
            conn.execute(
                """
                UPDATE attempts SET status = ?, finished_at = ?, retryable = ?,
                    error_code = ?, error_message = ?,
                    request_id = COALESCE(?, request_id), details_json = ?
                WHERE id = ?
                """,
                (
                    parsed.value,
                    _datetime_text(stamp),
                    None if retryable is None else int(retryable),
                    error_code,
                    error_message,
                    request_id,
                    details_json,
                    attempt_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
        return _attempt_from_row(row)

    def get_attempt(self, attempt_id: int) -> Attempt:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Attempt not found: {attempt_id}")
            return _attempt_from_row(row)

    def list_attempts(
        self, *, delivery_id: str | None = None, limit: int = 500
    ) -> list[Attempt]:
        if limit < 1 or limit > 5000:
            raise ValidationError("limit must be between 1 and 5000.")
        query = "SELECT * FROM attempts"
        params: list[Any] = []
        if delivery_id is not None:
            query += " WHERE delivery_id = ?"
            params.append(delivery_id)
        query += " ORDER BY started_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.db.connection() as conn:
            return [
                _attempt_from_row(row) for row in conn.execute(query, params).fetchall()
            ]

    # --------------------------------------------------------------- settings
    def set_setting(
        self, key: str, value: Any, *, now: datetime | None = None
    ) -> Setting:
        key = key.strip()
        if not key:
            raise ValidationError("Setting key is required.")
        stamp = _as_utc(now or _now(), field_name="now")
        encoded = _json_dump(value)
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, encoded, _datetime_text(stamp)),
            )
        return Setting(key=key, value=value, updated_at=stamp)

    def get_setting(self, key: str, default: Any = _MISSING) -> Any:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            if default is _MISSING:
                raise NotFoundError(f"Setting not found: {key}")
            return default
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Setting {key!r} contains invalid JSON.") from exc

    def list_settings(self) -> list[Setting]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM settings ORDER BY key").fetchall()
        return [
            Setting(
                key=row["key"],
                value=_json_load(row["value_json"], fallback=None),
                updated_at=_parse_datetime(row["updated_at"]),  # type: ignore[arg-type]
            )
            for row in rows
        ]

    def delete_setting(self, key: str) -> bool:
        with self.db.transaction(immediate=True) as conn:
            return (
                conn.execute("DELETE FROM settings WHERE key = ?", (key,)).rowcount == 1
            )

    # --------------------------------------------------------------- internals
    @staticmethod
    def _delivery_has_history(conn: sqlite3.Connection, delivery_id: str) -> bool:
        row = conn.execute(
            "SELECT attempt_count FROM deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Delivery not found: {delivery_id}")
        if int(row["attempt_count"]) > 0:
            return True
        return (
            conn.execute(
                "SELECT 1 FROM attempts WHERE delivery_id = ? LIMIT 1",
                (delivery_id,),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _assert_remote_ids_compatible(
        delivery: Delivery,
        *,
        remote_upload_id: str | None = None,
        remote_post_id: str | None = None,
    ) -> None:
        upload_id = remote_upload_id.strip() if remote_upload_id else None
        post_id = remote_post_id.strip() if remote_post_id else None
        if (
            upload_id
            and delivery.remote_upload_id
            and upload_id != delivery.remote_upload_id
        ):
            raise InvalidStateError(
                "A different remote upload id is already checkpointed."
            )
        if post_id and delivery.remote_post_id and post_id != delivery.remote_post_id:
            raise InvalidStateError(
                "A different remote post id is already checkpointed."
            )

    @staticmethod
    def _require_post_row(conn: sqlite3.Connection, post_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Post not found: {post_id}")
        return row

    @staticmethod
    def _require_delivery_row(
        conn: sqlite3.Connection, delivery_id: str
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Delivery not found: {delivery_id}")
        return row

    def _assert_current_approval(
        self, conn: sqlite3.Connection, post: Post, stamp: datetime
    ) -> None:
        actual_hash = compute_content_hash(
            video_path=post.video_path,
            video_sha256=post.video_sha256,
            caption=post.caption,
            hashtags=post.hashtags,
        )
        file_exists = Path(post.video_path).expanduser().is_file()
        if (
            not file_exists
            or not post.approval_hash
            or post.approval_hash != post.content_hash
            or actual_hash != post.content_hash
        ):
            self._invalidate_approval_locked(
                conn,
                post.id,
                actual_hash,
                stamp,
                error_code=(
                    "video_file_missing" if not file_exists else "approval_is_stale"
                ),
            )
            raise InvalidStateError(
                "The approved content no longer matches the current video/caption. "
                "Review and approve it again."
            )

    def _invalidate_approval_locked(
        self,
        conn: sqlite3.Connection,
        post_id: str,
        actual_hash: str,
        stamp: datetime,
        *,
        error_code: str,
    ) -> None:
        conn.execute(
            """
            UPDATE posts SET content_hash = ?, approval_hash = NULL,
                approved_at = NULL, scheduled_at = NULL, status = 'draft',
                updated_at = ? WHERE id = ?
            """,
            (actual_hash, _datetime_text(stamp), post_id),
        )
        conn.execute(
            """
            UPDATE deliveries SET status = 'pending', next_attempt_at = NULL,
                last_error_code = ?, last_error_message = ?,
                lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                updated_at = ?
            WHERE post_id = ? AND status IN ('pending', 'retry_wait', 'failed')
            """,
            (
                error_code,
                "Content or media changed after approval; approve it again.",
                _datetime_text(stamp),
                post_id,
            ),
        )

    def _set_destinations_locked(
        self,
        conn: sqlite3.Connection,
        post_id: str,
        destinations: Mapping[Platform | str, str | None] | Iterable[Platform | str],
        stamp: datetime,
    ) -> None:
        if isinstance(destinations, Mapping):
            desired = {_platform(key): value for key, value in destinations.items()}
        else:
            desired = {_platform(item): None for item in destinations}
        if not desired:
            raise ValidationError("At least one destination is required.")
        existing_rows = conn.execute(
            "SELECT * FROM deliveries WHERE post_id = ?", (post_id,)
        ).fetchall()
        existing = {
            Platform(row["platform"]): _delivery_from_row(row) for row in existing_rows
        }
        for platform, delivery in existing.items():
            if platform in desired:
                continue
            if delivery.lease_token:
                raise InvalidStateError(
                    f"Cannot remove {platform.value} while a worker owns it."
                )
            if delivery.status not in {
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
                DeliveryStatus.FAILED,
                DeliveryStatus.CANCELLED,
            }:
                raise InvalidStateError(
                    f"Cannot remove {platform.value} after publishing has begun."
                )
            has_attempt = conn.execute(
                "SELECT 1 FROM attempts WHERE delivery_id = ? LIMIT 1",
                (delivery.id,),
            ).fetchone()
            if has_attempt:
                conn.execute(
                    "UPDATE deliveries SET status = 'cancelled', "
                    "next_attempt_at = NULL, updated_at = ? WHERE id = ?",
                    (_datetime_text(stamp), delivery.id),
                )
            else:
                conn.execute("DELETE FROM deliveries WHERE id = ?", (delivery.id,))
        for platform, account_id in desired.items():
            desired_delivery = existing.get(platform)
            if desired_delivery is None:
                conn.execute(
                    """
                    INSERT INTO deliveries(
                        id, post_id, platform, account_id, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        uuid4().hex,
                        post_id,
                        platform.value,
                        account_id,
                        _datetime_text(stamp),
                        _datetime_text(stamp),
                    ),
                )
            else:
                if desired_delivery.status is DeliveryStatus.CANCELLED and (
                    desired_delivery.remote_upload_id
                    or desired_delivery.remote_post_id
                    or desired_delivery.remote_url
                    or self._delivery_has_history(conn, desired_delivery.id)
                ):
                    raise InvalidStateError(
                        f"Cancelled {platform.value} history cannot be reused."
                    )
                if (
                    account_id != desired_delivery.account_id
                    and desired_delivery.status
                    not in {
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRY_WAIT,
                        DeliveryStatus.FAILED,
                        DeliveryStatus.CANCELLED,
                    }
                ):
                    raise InvalidStateError(
                        f"Cannot change the {platform.value} account now."
                    )
                conn.execute(
                    "UPDATE deliveries SET account_id = ?, "
                    "status = CASE WHEN status = 'cancelled' THEN 'pending' "
                    "ELSE status END, updated_at = ? WHERE id = ?",
                    (account_id, _datetime_text(stamp), desired_delivery.id),
                )

    def _assert_valid_lease(
        self,
        conn: sqlite3.Connection,
        delivery_id: str,
        lease_token: str,
        stamp: datetime,
    ) -> Delivery:
        delivery = _delivery_from_row(self._require_delivery_row(conn, delivery_id))
        if (
            not lease_token
            or delivery.lease_token != lease_token
            or delivery.lease_expires_at is None
            or delivery.lease_expires_at <= stamp
        ):
            raise LeaseConflictError(
                "The worker lease is missing, expired, or belongs to another worker."
            )
        return delivery

    def _leased_transition(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        allowed: set[DeliveryStatus],
        new_status: DeliveryStatus,
        now: datetime | None,
        remote_upload_id: str | None,
    ) -> Delivery:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status not in allowed:
                raise InvalidStateError(
                    f"Cannot move {delivery.status.value} to {new_status.value}."
                )
            self._assert_remote_ids_compatible(
                delivery, remote_upload_id=remote_upload_id
            )
            conn.execute(
                """
                UPDATE deliveries SET status = ?,
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    last_error_code = NULL, last_error_message = NULL,
                    updated_at = ? WHERE id = ?
                """,
                (
                    new_status.value,
                    remote_upload_id,
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def _mark_terminal_error(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        status: DeliveryStatus,
        error_code: str,
        error_message: str,
        remote_upload_id: str | None,
        remote_post_id: str | None,
        now: datetime | None,
    ) -> Delivery:
        stamp = _as_utc(now or _now(), field_name="now")
        with self.db.transaction(immediate=True) as conn:
            delivery = self._assert_valid_lease(conn, delivery_id, lease_token, stamp)
            if delivery.status in {
                DeliveryStatus.PUBLISHED,
                DeliveryStatus.CANCELLED,
            }:
                raise InvalidStateError(
                    f"Cannot mark {delivery.status.value} as {status.value}."
                )
            self._assert_remote_ids_compatible(
                delivery,
                remote_upload_id=remote_upload_id,
                remote_post_id=remote_post_id,
            )
            conn.execute(
                """
                UPDATE deliveries SET status = ?, next_attempt_at = NULL,
                    remote_upload_id = COALESCE(remote_upload_id, ?),
                    remote_post_id = COALESCE(remote_post_id, ?),
                    last_error_code = ?, last_error_message = ?,
                    lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ? WHERE id = ?
                """,
                (
                    status.value,
                    remote_upload_id,
                    remote_post_id,
                    error_code,
                    error_message,
                    _datetime_text(stamp),
                    delivery_id,
                ),
            )
            self._recalculate_post_status(conn, delivery.post_id, stamp)
            row = self._require_delivery_row(conn, delivery_id)
        return _delivery_from_row(row)

    def _recalculate_post_status(
        self, conn: sqlite3.Connection, post_id: str, stamp: datetime
    ) -> PostStatus:
        post = _post_from_row(self._require_post_row(conn, post_id))
        rows = conn.execute(
            "SELECT status FROM deliveries WHERE post_id = ?", (post_id,)
        ).fetchall()
        statuses = [DeliveryStatus(row["status"]) for row in rows]
        live = [status for status in statuses if status is not DeliveryStatus.CANCELLED]
        if not post.is_approved:
            result = PostStatus.DRAFT
        elif live and all(status is DeliveryStatus.PUBLISHED for status in live):
            result = PostStatus.COMPLETED
        elif any(status is DeliveryStatus.PUBLISHED for status in live):
            result = PostStatus.PARTIAL
        elif any(status in _ACTIVE_DELIVERY_STATUSES for status in live):
            result = PostStatus.PUBLISHING
        elif any(
            status in {DeliveryStatus.NEEDS_ACTION, DeliveryStatus.UNKNOWN}
            for status in live
        ):
            result = PostStatus.NEEDS_ACTION
        elif live and all(status is DeliveryStatus.FAILED for status in live):
            result = PostStatus.FAILED
        elif post.scheduled_at is not None and any(
            status
            in {
                DeliveryStatus.PENDING,
                DeliveryStatus.RETRY_WAIT,
                DeliveryStatus.SCHEDULED,
            }
            for status in live
        ):
            result = PostStatus.SCHEDULED
        elif rows and not live:
            result = PostStatus.CANCELLED
        elif live:
            result = PostStatus.READY
        else:
            result = PostStatus.APPROVED
        conn.execute(
            "UPDATE posts SET status = ?, updated_at = ? WHERE id = ?",
            (result.value, _datetime_text(stamp), post_id),
        )
        return result
