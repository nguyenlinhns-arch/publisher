from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timedelta, timezone, tzinfo
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import AppConfig
from ..models import Delivery, DeliveryStatus, Platform, Post, PostStatus
from ..repository import Repository


class LinhMXHError(RuntimeError):
    """Safe-to-report error for the Linh MXH Hub action."""


@dataclass(frozen=True, slots=True)
class StreamSpec:
    stream_id: str
    destinations: Mapping[str, str | None]
    browser_profile_dir: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StreamSpec":
        stream_id = str(value.get("stream_id") or "").strip()
        if not stream_id:
            raise LinhMXHError("stream_id is required.")
        raw_destinations = value.get("destinations")
        if not isinstance(raw_destinations, Mapping) or not raw_destinations:
            raise LinhMXHError(f"{stream_id}: destinations are required.")
        destinations: dict[str, str | None] = {}
        for key, account_id in raw_destinations.items():
            try:
                platform = Platform(str(key).strip().lower())
            except ValueError as exc:
                raise LinhMXHError(
                    f"{stream_id}: unsupported platform {key!r}."
                ) from exc
            account = None if account_id is None else str(account_id).strip()
            if platform is Platform.FACEBOOK and (not account or not account.isdigit()):
                raise LinhMXHError(
                    f"{stream_id}: Facebook destination must be a numeric Page ID."
                )
            if platform is Platform.TIKTOK and not account:
                raise LinhMXHError(
                    f"{stream_id}: TikTok destination must identify an account."
                )
            destinations[platform.value] = account
        profile = value.get("browser_profile_dir")
        profile_text = None if profile is None else str(profile).strip() or None
        return cls(
            stream_id=stream_id,
            destinations=destinations,
            browser_profile_dir=profile_text,
        )

    def platform_destinations(self) -> dict[Platform, str | None]:
        return {Platform(key): value for key, value in self.destinations.items()}


@dataclass(frozen=True, slots=True)
class DualStreamRequest:
    video_title: str
    stream_2: StreamSpec
    stream_1: StreamSpec
    timezone_name: str = "Asia/Ho_Chi_Minh"
    preferred_time: str = "09:00"
    stream_1_offset_days: int = 2
    minimum_lead_minutes: int = 60
    search_horizon_days: int = 365
    commit: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DualStreamRequest":
        action = str(value.get("action") or "schedule_video_dual_stream").strip()
        if action != "schedule_video_dual_stream":
            raise LinhMXHError(f"Unsupported action: {action}")
        title = str(value.get("video_title") or "").strip()
        if not title:
            raise LinhMXHError("video_title is required.")
        stream_2_raw = value.get("stream_2")
        stream_1_raw = value.get("stream_1")
        if not isinstance(stream_2_raw, Mapping) or not isinstance(
            stream_1_raw, Mapping
        ):
            raise LinhMXHError("stream_2 and stream_1 are required.")
        return cls(
            video_title=title,
            stream_2=StreamSpec.from_mapping(stream_2_raw),
            stream_1=StreamSpec.from_mapping(stream_1_raw),
            timezone_name=str(
                value.get("timezone_name") or "Asia/Ho_Chi_Minh"
            ).strip(),
            preferred_time=str(value.get("preferred_time") or "09:00").strip(),
            stream_1_offset_days=int(value.get("stream_1_offset_days", 2)),
            minimum_lead_minutes=int(value.get("minimum_lead_minutes", 60)),
            search_horizon_days=int(value.get("search_horizon_days", 365)),
            commit=bool(value.get("commit", True)),
        )


@dataclass(frozen=True, slots=True)
class PlannedSlot:
    stream_id: str
    scheduled_at: datetime
    existing_post_id: str | None = None

    @property
    def existing(self) -> bool:
        return self.existing_post_id is not None


@dataclass(frozen=True, slots=True)
class DualStreamPlan:
    source_post_id: str
    video_title: str
    stream_2: PlannedSlot
    stream_1: PlannedSlot
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class DualStreamReceipt:
    action: str
    job_id: str
    idempotency_key: str
    video_title: str
    source_post_id: str
    stream_2_post_id: str | None
    stream_2_scheduled_at: str
    stream_2_status: str
    stream_1_post_id: str | None
    stream_1_scheduled_at: str
    stream_1_status: str
    duplicate_check: str
    final_status: str
    remote: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


RemoteDispatcher = Callable[[str, StreamSpec], Mapping[str, Any]]


class RepositoryHubScheduler:
    """Dual-stream scheduler that operates without opening the MXH GUI."""

    def __init__(
        self,
        repository: Repository,
        request: DualStreamRequest,
        *,
        now: datetime | None = None,
    ) -> None:
        self.repository = repository
        self.request = request
        self.timezone = self._load_timezone(request.timezone_name)
        self.publish_time = self._parse_time(request.preferred_time)
        current = now or datetime.now(self.timezone)
        if current.tzinfo is None or current.utcoffset() is None:
            raise LinhMXHError("now must be timezone-aware.")
        self.now = current.astimezone(self.timezone)
        self._deliveries_cache: dict[str, list[Delivery]] = {}
        if request.stream_1_offset_days < 2:
            raise LinhMXHError("stream_1_offset_days must be at least 2.")
        if request.minimum_lead_minutes < 0:
            raise LinhMXHError("minimum_lead_minutes cannot be negative.")
        if not 1 <= request.search_horizon_days <= 3650:
            raise LinhMXHError("search_horizon_days must be between 1 and 3650.")

    @staticmethod
    def _load_timezone(name: str) -> tzinfo:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            if name == "Asia/Ho_Chi_Minh":
                # Vietnam is UTC+07 and does not currently observe DST.
                # Keep the headless Hub action dependency-free on Windows.
                return timezone(timedelta(hours=7), name)
            raise LinhMXHError(f"Invalid timezone: {name}") from exc

    @staticmethod
    def _parse_time(value: str) -> time:
        try:
            hour_text, minute_text = value.split(":", 1)
            result = time(hour=int(hour_text), minute=int(minute_text))
        except (TypeError, ValueError) as exc:
            raise LinhMXHError("preferred_time must be HH:MM.") from exc
        return result

    @staticmethod
    def _media_identity(post: Post) -> str:
        digest = (post.video_sha256 or "").strip().lower()
        if digest:
            return f"sha256:{digest}"
        return f"path:{Path(post.video_path).expanduser().resolve(strict=False)}"

    @staticmethod
    def _normalised_destinations(stream: StreamSpec) -> dict[Platform, str | None]:
        return stream.platform_destinations()

    def _resolve_source(self) -> Post:
        matches = [
            post
            for post in self.repository.list_posts(
                search=self.request.video_title, limit=1000
            )
            if post.title == self.request.video_title
        ]
        if not matches:
            raise LinhMXHError(
                f'No video matches the exact title "{self.request.video_title}".'
            )
        usable = [post for post in matches if Path(post.video_path).is_file()]
        if not usable:
            raise LinhMXHError("Exact-title posts exist but the video file is missing.")
        identities = {self._media_identity(post) for post in usable}
        if len(identities) != 1:
            raise LinhMXHError(
                "The exact title points to multiple different video files; "
                "refusing an ambiguous publish."
            )
        return usable[0]

    def _post_matches_stream(self, post: Post, stream: StreamSpec) -> bool:
        if post.status is PostStatus.CANCELLED:
            return False
        desired = self._normalised_destinations(stream)
        deliveries = self._deliveries_cache.get(post.id)
        if deliveries is None:
            _, deliveries = self.repository.get_post_with_deliveries(post.id)
            self._deliveries_cache[post.id] = deliveries
        for delivery in deliveries:
            if delivery.status is DeliveryStatus.CANCELLED:
                continue
            if (
                delivery.platform in desired
                and delivery.account_id == desired[delivery.platform]
            ):
                return True
        return False

    def _scheduled_posts(self) -> list[Post]:
        return [
            post
            for post in self.repository.list_posts(limit=1000)
            if post.scheduled_at is not None
            and post.status is not PostStatus.CANCELLED
        ]

    def _existing_same_media(
        self,
        source: Post,
        stream: StreamSpec,
        posts: list[Post],
    ) -> Post | None:
        identity = self._media_identity(source)
        matches = [
            post
            for post in posts
            if self._media_identity(post) == identity
            and self._post_matches_stream(post, stream)
        ]
        if len(matches) > 1:
            raise LinhMXHError(
                f"{stream.stream_id}: multiple existing schedules use this video."
            )
        return matches[0] if matches else None

    def _slot_datetime(self, day) -> datetime:
        return datetime.combine(day, self.publish_time, tzinfo=self.timezone)

    def _is_busy(
        self,
        stream: StreamSpec,
        candidate: datetime,
        posts: list[Post],
        *,
        ignore_post_id: str | None = None,
    ) -> bool:
        target_day = candidate.date()
        for post in posts:
            if post.id == ignore_post_id or post.scheduled_at is None:
                continue
            local_due = post.scheduled_at.astimezone(self.timezone)
            if local_due.date() != target_day:
                continue
            if self._post_matches_stream(post, stream):
                return True
        return False

    def _first_candidate(self, preferred_day) -> datetime:
        candidate = self._slot_datetime(preferred_day)
        lead = timedelta(minutes=self.request.minimum_lead_minutes)
        if candidate < self.now + lead:
            candidate = self._slot_datetime(preferred_day + timedelta(days=1))
        return candidate

    def _next_free(
        self,
        stream: StreamSpec,
        preferred_day,
        posts: list[Post],
    ) -> datetime:
        candidate = self._first_candidate(preferred_day)
        for _ in range(self.request.search_horizon_days):
            if not self._is_busy(stream, candidate, posts):
                return candidate
            candidate = self._slot_datetime(candidate.date() + timedelta(days=1))
        raise LinhMXHError(
            f"{stream.stream_id}: no free day within "
            f"{self.request.search_horizon_days} days."
        )

    def _validate_existing_stream_1(
        self,
        existing: Post,
        minimum_day,
    ) -> datetime:
        if existing.scheduled_at is None:
            raise LinhMXHError("Existing stream 1 post has no schedule.")
        due = existing.scheduled_at.astimezone(self.timezone)
        if due.date() < minimum_day or due.time().replace(second=0, microsecond=0) != (
            self.publish_time
        ):
            raise LinhMXHError(
                f"{self.request.stream_1.stream_id}: this video already exists "
                "outside the Linh MXH +2-day/09:00 policy; refusing a duplicate."
            )
        return due

    def plan(self) -> DualStreamPlan:
        source = self._resolve_source()
        posts = self._scheduled_posts()

        existing_2 = self._existing_same_media(
            source, self.request.stream_2, posts
        )
        if existing_2 is not None:
            assert existing_2.scheduled_at is not None
            stream_2_due = existing_2.scheduled_at.astimezone(self.timezone)
        else:
            stream_2_due = self._next_free(
                self.request.stream_2, self.now.date(), posts
            )

        minimum_stream_1_day = (
            stream_2_due.date()
            + timedelta(days=self.request.stream_1_offset_days)
        )
        existing_1 = self._existing_same_media(
            source, self.request.stream_1, posts
        )
        if existing_1 is not None:
            stream_1_due = self._validate_existing_stream_1(
                existing_1, minimum_stream_1_day
            )
        else:
            stream_1_due = self._next_free(
                self.request.stream_1, minimum_stream_1_day, posts
            )

        canonical = {
            "action": "schedule_video_dual_stream",
            "media": self._media_identity(source),
            "stream_2": {
                "id": self.request.stream_2.stream_id,
                "destinations": dict(self.request.stream_2.destinations),
                "scheduled_at": stream_2_due.isoformat(),
            },
            "stream_1": {
                "id": self.request.stream_1.stream_id,
                "destinations": dict(self.request.stream_1.destinations),
                "scheduled_at": stream_1_due.isoformat(),
            },
            "title": source.title,
        }
        encoded = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        idem = sha256(encoded.encode("utf-8")).hexdigest()
        return DualStreamPlan(
            source_post_id=source.id,
            video_title=source.title,
            stream_2=PlannedSlot(
                stream_id=self.request.stream_2.stream_id,
                scheduled_at=stream_2_due,
                existing_post_id=existing_2.id if existing_2 else None,
            ),
            stream_1=PlannedSlot(
                stream_id=self.request.stream_1.stream_id,
                scheduled_at=stream_1_due,
                existing_post_id=existing_1.id if existing_1 else None,
            ),
            idempotency_key=idem,
        )

    def _clone_and_schedule(
        self,
        source: Post,
        stream: StreamSpec,
        due: datetime,
    ) -> Post:
        if self._is_busy(stream, due, self._scheduled_posts()):
            raise LinhMXHError(
                f"{stream.stream_id}: selected day became busy during commit."
            )
        created = self.repository.create_post(
            video_path=source.video_path,
            video_sha256=source.video_sha256,
            caption=source.caption,
            hashtags=source.hashtags,
            title=source.title,
            timezone_name=self.request.timezone_name,
        )
        try:
            self.repository.approve_post(created.id)
            return self.repository.schedule_post(
                created.id,
                due,
                destinations=self._normalised_destinations(stream),
                now=self.now,
            )
        except Exception:
            try:
                self.repository.delete_post(created.id)
            except Exception:
                pass
            raise

    def _rollback_local(self, post_ids: list[str]) -> None:
        for post_id in reversed(post_ids):
            try:
                self.repository.cancel_schedule(post_id, now=self.now)
            except Exception:
                pass
            try:
                self.repository.delete_post(post_id)
            except Exception:
                pass

    def execute(
        self,
        *,
        remote_dispatcher: RemoteDispatcher | None = None,
    ) -> DualStreamReceipt:
        plan = self.plan()
        receipt_key = f"linh_mxh.receipt.{plan.idempotency_key}"
        cached = self.repository.get_setting(receipt_key, default=None)
        if isinstance(cached, Mapping):
            try:
                cached_receipt = DualStreamReceipt(**dict(cached))
            except TypeError:
                cached_receipt = None
            if cached_receipt is not None and cached_receipt.final_status in {
                "DONE",
                "DONE_EXISTING",
            }:
                return cached_receipt

        source = self.repository.get_post(plan.source_post_id)
        if not self.request.commit:
            return DualStreamReceipt(
                action="schedule_video_dual_stream",
                job_id=plan.idempotency_key[:16],
                idempotency_key=plan.idempotency_key,
                video_title=plan.video_title,
                source_post_id=plan.source_post_id,
                stream_2_post_id=plan.stream_2.existing_post_id,
                stream_2_scheduled_at=plan.stream_2.scheduled_at.isoformat(),
                stream_2_status="EXISTING"
                if plan.stream_2.existing
                else "PLANNED",
                stream_1_post_id=plan.stream_1.existing_post_id,
                stream_1_scheduled_at=plan.stream_1.scheduled_at.isoformat(),
                stream_1_status="EXISTING"
                if plan.stream_1.existing
                else "PLANNED",
                duplicate_check="PASS",
                final_status="PLANNED",
                remote={},
            )

        created_ids: list[str] = []
        stream_2_post_id = plan.stream_2.existing_post_id
        stream_1_post_id = plan.stream_1.existing_post_id
        try:
            if stream_2_post_id is None:
                created = self._clone_and_schedule(
                    source, self.request.stream_2, plan.stream_2.scheduled_at
                )
                stream_2_post_id = created.id
                created_ids.append(created.id)
            if stream_1_post_id is None:
                created = self._clone_and_schedule(
                    source, self.request.stream_1, plan.stream_1.scheduled_at
                )
                stream_1_post_id = created.id
                created_ids.append(created.id)
        except Exception:
            self._rollback_local(created_ids)
            raise

        remote: dict[str, Any] = {}
        stream_2_status = "EXISTING" if plan.stream_2.existing else "PREPARED"
        stream_1_status = "EXISTING" if plan.stream_1.existing else "PREPARED"
        # A local schedule is not a provider receipt. Existing local rows remain
        # PREPARED until MXH Video Tool readback confirms the remote state.
        final_status = "PREPARED"
        if remote_dispatcher is not None:
            dispatch_errors = False
            for key, post_id, stream, existing in (
                (
                    "stream_2",
                    stream_2_post_id,
                    self.request.stream_2,
                    plan.stream_2.existing,
                ),
                (
                    "stream_1",
                    stream_1_post_id,
                    self.request.stream_1,
                    plan.stream_1.existing,
                ),
            ):
                if post_id is None:
                    continue
                if existing:
                    readback = getattr(remote_dispatcher, "readback", None)
                    if callable(readback):
                        try:
                            result = dict(readback(post_id, stream))
                        except Exception as exc:
                            result = {"status": "ERROR", "error": str(exc)}
                            dispatch_errors = True
                    else:
                        result = {
                            "status": "SUBMITTED_UNVERIFIED",
                            "message": (
                                "Local schedule exists but MXH Video Tool readback "
                                "is unavailable; no mutation was replayed."
                            ),
                        }

                    # Only delivery states that prove no unsafe remote mutation
                    # is in flight may be resumed automatically. This also
                    # supports partial recovery: a scheduled/published platform
                    # is preserved while only pending/retry_wait destinations run.
                    deliveries = result.get("deliveries")
                    states = (
                        {str(value).lower() for value in deliveries.values()}
                        if isinstance(deliveries, Mapping)
                        else set()
                    )
                    safe_recovery_states = {
                        "pending",
                        "retry_wait",
                        "scheduled",
                        "published",
                    }
                    retryable_states = {"pending", "retry_wait"}
                    if (
                        str(result.get("status") or "").upper() == "PREPARED"
                        and states
                        and states <= safe_recovery_states
                        and states & retryable_states
                    ):
                        try:
                            result = dict(remote_dispatcher(post_id, stream))
                        except Exception as exc:
                            result = {"status": "ERROR", "error": str(exc)}
                            dispatch_errors = True
                    remote[key] = result
                    continue
                try:
                    result = dict(remote_dispatcher(post_id, stream))
                except Exception as exc:
                    result = {"status": "ERROR", "error": str(exc)}
                    dispatch_errors = True
                remote[key] = result
            statuses = {
                str(item.get("status") or "").upper()
                for item in remote.values()
                if isinstance(item, Mapping)
            }
            if dispatch_errors or statuses & {"ERROR", "FAILED"}:
                final_status = "PARTIAL"
            elif statuses and statuses <= {"SCHEDULED", "PUBLISHED"}:
                final_status = (
                    "DONE_EXISTING"
                    if plan.stream_2.existing and plan.stream_1.existing
                    else "DONE"
                )
            elif statuses & {
                "UNKNOWN",
                "SUBMITTED_UNVERIFIED",
                "PROCESSING",
                "PREPARING",
                "UPLOADING",
                "AWAITING_CONFIRMATION",
            }:
                # Mutation may already have reached the provider. This is not a
                # retryable failure and must only advance through readback.
                final_status = "SUBMITTED_UNVERIFIED"
            elif statuses & {"NEEDS_ACTION", "RETRY_WAIT"}:
                final_status = "NEEDS_ACTION"
            elif statuses:
                final_status = "NEEDS_ACTION"
            else:
                final_status = "PREPARED"
            stream_2_status = str(
                remote.get("stream_2", {}).get("status") or stream_2_status
            )
            stream_1_status = str(
                remote.get("stream_1", {}).get("status") or stream_1_status
            )

        receipt = DualStreamReceipt(
            action="schedule_video_dual_stream",
            job_id=plan.idempotency_key[:16],
            idempotency_key=plan.idempotency_key,
            video_title=plan.video_title,
            source_post_id=plan.source_post_id,
            stream_2_post_id=stream_2_post_id,
            stream_2_scheduled_at=plan.stream_2.scheduled_at.isoformat(),
            stream_2_status=stream_2_status,
            stream_1_post_id=stream_1_post_id,
            stream_1_scheduled_at=plan.stream_1.scheduled_at.isoformat(),
            stream_1_status=stream_1_status,
            duplicate_check="PASS",
            final_status=final_status,
            remote=remote,
        )
        self.repository.set_setting(receipt_key, receipt.as_dict(), now=self.now)
        return receipt


class OrchestratorDispatcher:
    """MXH Video Tool backend executor used by Hub's videoPublish bridge.

    The Hub owns planning, idempotency and orchestration. Remote mutations stay
    inside the MXH Video Tool publishing backend and are never treated as
    successful until delivery readback reaches scheduled/published.
    """

    def __init__(
        self,
        repository: Repository,
        base_config: AppConfig,
    ) -> None:
        self.repository = repository
        self.base_config = base_config

    def __call__(self, post_id: str, stream: StreamSpec) -> Mapping[str, Any]:
        from .orchestrator import OrchestrationError, PublishingOrchestrator

        destinations = stream.platform_destinations()
        page_id = destinations.get(
            Platform.FACEBOOK, self.base_config.facebook_page_id
        )
        tiktok_id = destinations.get(
            Platform.TIKTOK, self.base_config.tiktok_account_id
        )
        config = replace(
            self.base_config,
            facebook_page_id=str(page_id or ""),
            tiktok_account_id=str(tiktok_id or ""),
            browser_profile_dir=Path(stream.browser_profile_dir)
            if stream.browser_profile_dir
            else self.base_config.browser_profile_dir,
        )
        orchestrator = PublishingOrchestrator(self.repository, config)
        messages: list[str] = []
        platform_errors: dict[str, str] = {}
        done_states = {DeliveryStatus.SCHEDULED, DeliveryStatus.PUBLISHED}
        safe_attempt_states = {DeliveryStatus.PENDING, DeliveryStatus.RETRY_WAIT}
        unsafe_replay_states = {
            DeliveryStatus.PREPARING,
            DeliveryStatus.UPLOADING,
            DeliveryStatus.PROCESSING,
            DeliveryStatus.AWAITING_CONFIRMATION,
            DeliveryStatus.UNKNOWN,
        }
        actions = (
            (Platform.TIKTOK, orchestrator.prepare_tiktok),
            (Platform.FACEBOOK, orchestrator.schedule_facebook),
        )
        try:
            for platform, action in actions:
                if platform not in destinations:
                    continue
                delivery = self.repository.get_delivery_for_platform(
                    post_id, platform
                )
                if delivery.status in done_states:
                    messages.append(
                        f"{platform.value}: đã xác nhận {delivery.status.value}; bỏ qua."
                    )
                    continue
                if delivery.status in unsafe_replay_states:
                    messages.append(
                        f"{platform.value}: {delivery.status.value}; chỉ đối soát, không gửi lại."
                    )
                    continue
                if delivery.status not in safe_attempt_states:
                    platform_errors[platform.value] = (
                        f"Trạng thái {delivery.status.value}; không tự động gửi lại."
                    )
                    continue
                try:
                    result = action(post_id)
                    messages.append(result.message)
                except OrchestrationError as exc:
                    # A failure on one destination must not block an independent
                    # destination in the same stream. Its repository state
                    # decides whether a later run may retry safely.
                    platform_errors[platform.value] = str(exc)
        finally:
            orchestrator.close()
        deliveries = self._delivery_states(post_id, destinations)
        response: dict[str, Any] = {
            "status": self._classify_delivery_states(deliveries),
            "message": " ".join(messages).strip(),
            "deliveries": deliveries,
            "bridge": "video_publish_bridge",
            "executor": "mxh_video_tool",
        }
        if platform_errors:
            response["errors"] = platform_errors
        return response

    def readback(self, post_id: str, stream: StreamSpec) -> Mapping[str, Any]:
        """Read MXH Video Tool delivery state without issuing a provider mutation."""

        destinations = stream.platform_destinations()
        deliveries = self._delivery_states(post_id, destinations)
        return {
            "status": self._classify_delivery_states(deliveries),
            "message": "MXH Video Tool readback only; no remote mutation issued.",
            "deliveries": deliveries,
            "bridge": "video_publish_bridge",
            "executor": "mxh_video_tool",
        }

    @staticmethod
    def _classify_delivery_states(deliveries: Mapping[str, str]) -> str:
        states = {str(value).lower() for value in deliveries.values()}
        if states and states <= {"scheduled", "published"}:
            return "SCHEDULED"
        if "failed" in states:
            return "ERROR"
        if states & {
            "unknown",
            "processing",
            "preparing",
            "uploading",
            "awaiting_confirmation",
        }:
            return "SUBMITTED_UNVERIFIED"
        if "needs_action" in states:
            return "NEEDS_ACTION"
        safe_recovery_states = {
            "pending",
            "retry_wait",
            "scheduled",
            "published",
        }
        if (
            states
            and states <= safe_recovery_states
            and states & {"pending", "retry_wait"}
        ):
            return "PREPARED"
        return "PREPARED"

    def _delivery_states(
        self,
        post_id: str,
        destinations: Mapping[Platform, str | None],
    ) -> dict[str, str]:
        states: dict[str, str] = {}
        for platform in destinations:
            delivery = self.repository.get_delivery_for_platform(post_id, platform)
            states[platform.value] = delivery.status.value
        return states


def schedule_video_dual_stream(
    repository: Repository,
    request: DualStreamRequest | Mapping[str, Any],
    *,
    now: datetime | None = None,
    remote_dispatcher: RemoteDispatcher | None = None,
) -> DualStreamReceipt:
    parsed = (
        request
        if isinstance(request, DualStreamRequest)
        else DualStreamRequest.from_mapping(request)
    )
    return RepositoryHubScheduler(repository, parsed, now=now).execute(
        remote_dispatcher=remote_dispatcher
    )
