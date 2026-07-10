from __future__ import annotations

import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..config import AppConfig
from ..models import AttemptStatus, DeliveryStatus, Platform, Post
from ..publishers.base import (
    PublishCheckpoint,
    PublishCheckpointCallback,
    PublishRequest,
    PublishResult,
    PublisherError,
)
from ..publishers.facebook import FacebookPublisher
from ..publishers.tiktok import (
    STATE_AWAITING_CONFIRMATION,
    TikTokPublisher,
)
from ..repository import Repository
from ..secrets import FACEBOOK_TOKEN_NAME, SecretStore
from .dry_run import DryRunReport, run_dry_run
from .lease import LeaseHeartbeat, LeaseHeartbeatError


LOGGER = logging.getLogger(__name__)
REMOTE_MUTATION_LEASE_SECONDS = 3600


class OrchestrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActionResult:
    message: str
    post: Post
    platform_result: PublishResult | None = None


FacebookFactory = Callable[[PublishCheckpointCallback | None], FacebookPublisher]


def combined_caption(post: Post) -> str:
    hashtags = " ".join(post.hashtags)
    return (post.caption.strip() + ("\n\n" + hashtags if hashtags else "")).strip()


class PublishingOrchestrator:
    """Coordinates state changes; adapters never write SQLite directly."""

    def __init__(
        self,
        repository: Repository,
        config: AppConfig,
        *,
        tiktok: TikTokPublisher | None = None,
        facebook_factory: FacebookFactory | None = None,
        secret_store: SecretStore | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.repository = repository
        self.config = config
        self.secret_store = secret_store or SecretStore()
        self.worker_id = worker_id or f"{socket.gethostname()}-{id(self):x}"
        self.tiktok = tiktok or TikTokPublisher(
            browser_profile_dir=config.browser_profile_dir / "tiktok",
            screenshots_dir=config.screenshots_dir / "tiktok",
            upload_url=config.tiktok_upload_url,
            browser_channel=config.browser_channel,
        )
        self.facebook_factory = facebook_factory

    def close(self) -> None:
        self.tiktok.close()

    def _default_facebook_factory(
        self,
        checkpoint_callback: PublishCheckpointCallback | None = None,
    ) -> FacebookPublisher:
        if not self.config.facebook_page_id.strip():
            raise OrchestrationError("Chưa cấu hình Facebook Page ID.")

        def token_provider() -> str:
            token = self.secret_store.get(FACEBOOK_TOKEN_NAME)
            if not token:
                raise OrchestrationError("Chưa lưu Facebook Page access token.")
            return token

        return FacebookPublisher(
            page_id=self.config.facebook_page_id,
            token_provider=token_provider,
            checkpoint_callback=checkpoint_callback,
        )

    def _facebook_publisher(
        self,
        checkpoint_callback: PublishCheckpointCallback | None = None,
    ) -> FacebookPublisher:
        if self.facebook_factory is not None:
            return self.facebook_factory(checkpoint_callback)
        return self._default_facebook_factory(checkpoint_callback)

    def assert_platform_setup(self) -> None:
        if not self.config.facebook_page_id.strip():
            raise OrchestrationError("Chưa cấu hình Facebook Page ID.")
        token = self.secret_store.get(FACEBOOK_TOKEN_NAME)
        if not token:
            raise OrchestrationError("Chưa lưu Facebook Page access token.")

    def dry_run(self, post_id: str) -> DryRunReport:
        post = self.repository.get_post(post_id)
        if post.scheduled_at is None:
            raise OrchestrationError("Bài chưa có thời gian đăng.")
        if not post.video_sha256:
            raise OrchestrationError("Bài chưa có SHA-256 của video.")
        return run_dry_run(
            video_path=Path(post.video_path),
            expected_sha256=post.video_sha256,
            caption=post.caption,
            hashtags=" ".join(post.hashtags),
            scheduled_at_utc=post.scheduled_at,
            approved=post.is_approved,
            minimum_lead_minutes=self.config.minimum_schedule_lead_minutes,
            caption_soft_limit=self.config.caption_soft_limit,
        )

    def prepare_tiktok(self, post_id: str) -> ActionResult:
        self.assert_platform_setup()
        report = self.dry_run(post_id)
        if not report.ready:
            raise OrchestrationError(report.as_text())
        post = self.repository.get_post(post_id)
        delivery = self.repository.get_delivery_for_platform(post_id, Platform.TIKTOK)
        if delivery.status not in {
            DeliveryStatus.PENDING,
            DeliveryStatus.RETRY_WAIT,
        }:
            raise OrchestrationError(
                f"TikTok đang ở trạng thái {delivery.status.value}; không upload lại."
            )
        claimed = self.repository.claim_delivery(
            delivery.id,
            self.worker_id,
            lease_seconds=REMOTE_MUTATION_LEASE_SECONDS,
        )
        token = claimed.lease_token or ""
        attempt = self.repository.begin_attempt(
            delivery.id, token, phase="prepare_tiktok", details={"mode": "assisted"}
        )
        self.repository.mark_preparing(delivery.id, token)
        request = PublishRequest(
            post_id=post.id,
            video_path=Path(post.video_path),
            caption=combined_caption(post),
            scheduled_at_utc=post.scheduled_at,
            options={"timezone": post.timezone},
        )
        try:
            result = self.tiktok.publish(request)
            if result.state == STATE_AWAITING_CONFIRMATION:
                self.repository.mark_awaiting_confirmation(
                    delivery.id,
                    token,
                    next_check_at=post.scheduled_at,
                )
                self.repository.finish_attempt(
                    attempt.id,
                    AttemptStatus.SUCCEEDED,
                    retryable=False,
                    details=dict(result.metadata),
                )
                return ActionResult(
                    result.message, self.repository.get_post(post_id), result
                )

            self.repository.mark_needs_action(
                delivery.id,
                token,
                error_code=f"tiktok.{result.state}",
                error_message=result.message,
            )
            self.repository.finish_attempt(
                attempt.id,
                AttemptStatus.FAILED,
                retryable=False,
                error_code=f"tiktok.{result.state}",
                error_message=result.message,
                details=dict(result.metadata),
            )
            return ActionResult(
                result.message, self.repository.get_post(post_id), result
            )
        except PublisherError as exc:
            if exc.unknown_outcome:
                self.repository.mark_unknown(
                    delivery.id,
                    token,
                    error_code=exc.code,
                    error_message=exc.message,
                )
                attempt_status = AttemptStatus.UNKNOWN
            else:
                self.repository.mark_needs_action(
                    delivery.id,
                    token,
                    error_code=exc.code,
                    error_message=exc.message,
                )
                attempt_status = AttemptStatus.FAILED
            self.repository.finish_attempt(
                attempt.id,
                attempt_status,
                retryable=False,
                error_code=exc.code,
                error_message=exc.message,
                details=exc.metadata,
            )
            raise OrchestrationError(exc.message) from exc

    def confirm_tiktok_and_schedule_facebook(self, post_id: str) -> ActionResult:
        """Record the human TikTok confirmation, then schedule Facebook."""

        self.assert_platform_setup()
        post = self.repository.get_post(post_id)
        if post.scheduled_at is None:
            raise OrchestrationError("Bài chưa có thời gian đăng.")
        tiktok = self.repository.get_delivery_for_platform(post_id, Platform.TIKTOK)
        if tiktok.status is DeliveryStatus.AWAITING_CONFIRMATION:
            claimed_tiktok = self.repository.claim_delivery(tiktok.id, self.worker_id)
            self.repository.mark_scheduled(
                tiktok.id,
                claimed_tiktok.lease_token or "",
                next_check_at=post.scheduled_at,
            )
        elif tiktok.status is not DeliveryStatus.SCHEDULED:
            raise OrchestrationError(
                "TikTok chưa ở màn hình chờ xác nhận. Không lên lịch Facebook."
            )

        facebook_delivery = self.repository.get_delivery_for_platform(
            post_id, Platform.FACEBOOK
        )
        if facebook_delivery.status is DeliveryStatus.SCHEDULED:
            return ActionResult(
                "TikTok và Facebook đều đã được ghi nhận là đã lên lịch.",
                self.repository.get_post(post_id),
            )
        if facebook_delivery.status not in {
            DeliveryStatus.PENDING,
            DeliveryStatus.RETRY_WAIT,
        }:
            raise OrchestrationError(
                f"Facebook đang ở trạng thái {facebook_delivery.status.value}; không gửi lại."
            )

        claimed = self.repository.claim_delivery(
            facebook_delivery.id,
            self.worker_id,
            lease_seconds=REMOTE_MUTATION_LEASE_SECONDS,
        )
        lease_token = claimed.lease_token or ""
        attempt = self.repository.begin_attempt(
            facebook_delivery.id,
            lease_token,
            phase="schedule_facebook",
            details={"graph_version": self.config.graph_version},
        )
        self.repository.mark_preparing(facebook_delivery.id, lease_token)

        def save_checkpoint(checkpoint: PublishCheckpoint) -> None:
            self.repository.checkpoint_remote_id(
                facebook_delivery.id,
                lease_token,
                remote_upload_id=checkpoint.remote_id,
            )
            self.repository.renew_lease(
                facebook_delivery.id,
                lease_token,
                lease_seconds=REMOTE_MUTATION_LEASE_SECONDS,
            )

        publisher: FacebookPublisher | None = None
        try:
            publisher = self._facebook_publisher(save_checkpoint)
            with LeaseHeartbeat(
                self.repository,
                facebook_delivery.id,
                lease_token,
                lease_seconds=REMOTE_MUTATION_LEASE_SECONDS,
                interval_seconds=60,
            ):
                result = publisher.publish(
                    PublishRequest(
                        post_id=post.id,
                        video_path=Path(post.video_path),
                        caption=combined_caption(post),
                        scheduled_at_utc=post.scheduled_at,
                        options={},
                    )
                )
            video_id = (
                str(result.metadata.get("video_id") or result.remote_id or "") or None
            )
            post_remote_id = str(result.metadata.get("post_id") or "") or None
            if result.state == "scheduled":
                self.repository.mark_scheduled(
                    facebook_delivery.id,
                    lease_token,
                    remote_upload_id=video_id,
                    remote_post_id=post_remote_id,
                    remote_url=result.permalink_url,
                    next_check_at=post.scheduled_at,
                )
            elif result.state == "published":
                self.repository.mark_published(
                    facebook_delivery.id,
                    lease_token,
                    remote_upload_id=video_id,
                    remote_post_id=post_remote_id
                    or result.remote_id
                    or video_id
                    or "facebook-post",
                    remote_url=result.permalink_url,
                )
            else:
                self.repository.mark_processing(
                    facebook_delivery.id,
                    lease_token,
                    remote_upload_id=video_id,
                    next_check_at=datetime.now(UTC) + timedelta(minutes=15),
                )
            self.repository.finish_attempt(
                attempt.id,
                AttemptStatus.SUCCEEDED,
                retryable=False,
                details=dict(result.metadata),
            )
            return ActionResult(
                result.message, self.repository.get_post(post_id), result
            )
        except PublisherError as exc:
            error_video_id = str(exc.metadata.get("video_id") or "") or None
            if exc.unknown_outcome:
                self.repository.mark_unknown(
                    facebook_delivery.id,
                    lease_token,
                    remote_upload_id=error_video_id,
                    error_code=exc.code,
                    error_message=exc.message,
                )
                status = AttemptStatus.UNKNOWN
            else:
                self.repository.mark_needs_action(
                    facebook_delivery.id,
                    lease_token,
                    error_code=exc.code,
                    error_message=exc.message,
                    remote_upload_id=error_video_id,
                )
                status = AttemptStatus.FAILED
            self.repository.finish_attempt(
                attempt.id,
                status,
                retryable=False,
                error_code=exc.code,
                error_message=exc.message,
                details=exc.metadata,
            )
            raise OrchestrationError(
                "TikTok đã được xác nhận nhưng Facebook chưa lên lịch: " + exc.message
            ) from exc
        except LeaseHeartbeatError as exc:
            current = self.repository.get_delivery(facebook_delivery.id)
            try:
                self.repository.mark_unknown(
                    facebook_delivery.id,
                    lease_token,
                    remote_upload_id=current.remote_upload_id,
                    remote_post_id=current.remote_post_id,
                    error_code="lease_heartbeat_failed",
                    error_message=str(exc),
                )
            except Exception:
                LOGGER.exception(
                    "Could not persist UNKNOWN after lease heartbeat failure",
                    extra={"delivery_id": facebook_delivery.id},
                )
            self.repository.finish_attempt(
                attempt.id,
                AttemptStatus.UNKNOWN,
                retryable=False,
                error_code="lease_heartbeat_failed",
                error_message=str(exc),
            )
            raise OrchestrationError(
                "Mất kết nối gia hạn trạng thái khi Facebook đang upload; bắt buộc "
                "đối soát trước khi thao tác lại."
            ) from exc
        finally:
            if publisher is not None:
                publisher.close()

    def record_manual_published(
        self,
        post_id: str,
        platform: Platform,
        *,
        remote_post_id: str,
        permalink_url: str | None = None,
    ) -> ActionResult:
        delivery = self.repository.get_delivery_for_platform(post_id, platform)
        if delivery.status is DeliveryStatus.PUBLISHED:
            return ActionResult(
                "Bài đã được ghi nhận trước đó.", self.repository.get_post(post_id)
            )
        self.repository.resolve_as_published(
            delivery.id,
            remote_post_id=remote_post_id.strip(),
            url=(permalink_url or "").strip() or None,
            confirmed_by="local_gui_user",
        )
        return ActionResult(
            "Đã ghi nhận bài đăng và đường dẫn.", self.repository.get_post(post_id)
        )

    def requeue_after_manual_check(
        self, post_id: str, platform: Platform
    ) -> ActionResult:
        delivery = self.repository.get_delivery_for_platform(post_id, platform)
        self.repository.requeue_delivery(
            delivery.id,
            confirmed_no_remote=True,
            next_attempt_at=datetime.now(UTC),
        )
        return ActionResult(
            "Đã đưa tác vụ về hàng chờ sau kiểm tra thủ công.",
            self.repository.get_post(post_id),
        )

    def verify_one_due_facebook(self) -> bool:
        delivery = self.repository.claim_due_delivery(
            self.worker_id,
            platforms=[Platform.FACEBOOK],
        )
        if delivery is None:
            return False
        token = delivery.lease_token or ""
        if not delivery.remote_upload_id:
            self.repository.mark_needs_action(
                delivery.id,
                token,
                error_code="facebook.missing_video_id",
                error_message="Không có video_id để đối soát Facebook.",
            )
            return True
        attempt = self.repository.begin_attempt(
            delivery.id, token, phase="verify_facebook"
        )
        publisher = self._facebook_publisher()
        try:
            result = publisher.verify(
                delivery.remote_upload_id,
                post_id=delivery.remote_post_id,
            )
            if result.state == "published":
                self.repository.mark_published(
                    delivery.id,
                    token,
                    remote_upload_id=delivery.remote_upload_id,
                    remote_post_id=result.remote_id
                    or delivery.remote_post_id
                    or delivery.remote_upload_id,
                    remote_url=result.permalink_url or delivery.remote_url,
                )
            else:
                self.repository.mark_processing(
                    delivery.id,
                    token,
                    remote_upload_id=delivery.remote_upload_id,
                    next_check_at=datetime.now(UTC) + timedelta(minutes=15),
                )
            self.repository.finish_attempt(
                attempt.id,
                AttemptStatus.SUCCEEDED,
                retryable=False,
                details=dict(result.metadata),
            )
        except PublisherError as exc:
            if exc.unknown_outcome:
                self.repository.mark_unknown(
                    delivery.id, token, error_code=exc.code, error_message=exc.message
                )
                status = AttemptStatus.UNKNOWN
            else:
                self.repository.mark_needs_action(
                    delivery.id, token, error_code=exc.code, error_message=exc.message
                )
                status = AttemptStatus.FAILED
            self.repository.finish_attempt(
                attempt.id,
                status,
                retryable=False,
                error_code=exc.code,
                error_message=exc.message,
                details=exc.metadata,
            )
            LOGGER.warning(
                "Facebook verification failed: %s",
                exc.message,
                extra={
                    "delivery_id": delivery.id,
                    "platform": "facebook",
                    "error_code": exc.code,
                },
            )
        finally:
            publisher.close()
        return True
