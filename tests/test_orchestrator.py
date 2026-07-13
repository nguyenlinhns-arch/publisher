from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mxh_publisher.config import AppConfig
from mxh_publisher.models import DeliveryStatus, Platform, PostStatus
from mxh_publisher.publishers.base import (
    PublishCheckpoint,
    PublishResult,
    PublisherError,
)
from mxh_publisher.publishers.tiktok import (
    STATE_AUTHENTICATION_REQUIRED,
    STATE_AWAITING_CONFIRMATION,
    STATE_SCHEDULED,
)
from mxh_publisher.repository import InvalidStateError, Repository
from mxh_publisher.services.dry_run import CheckResult, DryRunReport
from mxh_publisher.services.media import sha256_file
from mxh_publisher.services.browser_connections import BrowserConnectionResult
from mxh_publisher.services.orchestrator import (
    OrchestrationError,
    PublishingOrchestrator,
)


class FakeSecrets:
    def get(self, _name: str) -> str:
        return "fake-token"


class EmptySecrets:
    def get(self, _name: str) -> str | None:
        return None


class FakeTikTok:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, request):
        self.calls.append(request)
        return PublishResult(
            state=STATE_AWAITING_CONFIRMATION,
            metadata={"publish_action_performed": False},
            message="Chờ người dùng xác nhận.",
        )

    def close(self) -> None:
        return None


class FakeAutomaticTikTok(FakeTikTok):
    def publish(self, request):
        self.calls.append(request)
        return PublishResult(
            state=STATE_SCHEDULED,
            remote_id="tiktok-scheduled-123",
            metadata={"schedule_action_performed": True},
            message="TikTok đã được lên lịch tự động.",
        )


class FakeLoginRequiredTikTok(FakeTikTok):
    def publish(self, request):
        self.calls.append(request)
        return PublishResult(
            state=STATE_AUTHENTICATION_REQUIRED,
            metadata={"phase": "before_upload", "publish_action_performed": False},
            message="Hãy đăng nhập TikTok.",
        )


class FakeFacebook:
    def __init__(self) -> None:
        self.publish_calls = []
        self.closed = 0
        self.checkpoint = None

    def publish(self, request):
        self.publish_calls.append(request)
        if self.checkpoint:
            self.checkpoint(
                PublishCheckpoint(
                    platform="facebook",
                    post_id=request.post_id,
                    stage="upload_initialized",
                    remote_id="video-123",
                )
            )
        return PublishResult(
            state="scheduled",
            remote_id="video-123",
            metadata={"video_id": "video-123", "post_id": None},
            message="Facebook đã nhận lịch.",
        )

    def verify(self, video_id: str, *, post_id: str | None = None):
        return PublishResult(
            state="published",
            remote_id=post_id or video_id,
            permalink_url="https://www.facebook.com/post",
            metadata={"video_id": video_id},
        )

    def verify_page_access(self):
        return {"id": "123456", "name": "Page thử"}

    def close(self) -> None:
        self.closed += 1


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        root_dir=tmp_path,
        database_path=tmp_path / "db.sqlite3",
        media_dir=tmp_path / "media",
        logs_dir=tmp_path / "logs",
        screenshots_dir=tmp_path / "screenshots",
        browser_profile_dir=tmp_path / "profile",
        facebook_page_id="123456",
        tiktok_account_id="@test_account",
    )


def test_tiktok_must_be_confirmed_before_facebook(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
        hashtags="#TKV",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )
    tiktok = FakeTikTok()
    facebook = FakeFacebook()

    def facebook_factory(checkpoint=None):
        facebook.checkpoint = checkpoint
        return facebook

    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=tiktok,
        facebook_factory=facebook_factory,
        secret_store=FakeSecrets(),
    )

    orchestrator.prepare_tiktok(post.id)
    assert len(tiktok.calls) == 1
    assert len(facebook.publish_calls) == 0
    assert (
        repository.get_delivery_for_platform(post.id, Platform.TIKTOK).status
        is DeliveryStatus.AWAITING_CONFIRMATION
    )

    orchestrator.confirm_tiktok_and_schedule_facebook(post.id)
    assert len(facebook.publish_calls) == 1
    assert (
        repository.get_delivery_for_platform(post.id, Platform.TIKTOK).status
        is DeliveryStatus.SCHEDULED
    )
    assert (
        repository.get_delivery_for_platform(post.id, Platform.FACEBOOK).status
        is DeliveryStatus.SCHEDULED
    )
    assert (
        repository.get_delivery_for_platform(
            post.id, Platform.FACEBOOK
        ).remote_upload_id
        == "video-123"
    )

    # Repeating the user action must not create another Facebook upload.
    orchestrator.confirm_tiktok_and_schedule_facebook(post.id)
    assert len(facebook.publish_calls) == 1

    orchestrator.record_manual_published(
        post.id,
        Platform.TIKTOK,
        remote_post_id="tt-123",
        permalink_url="https://www.tiktok.com/@test/video/123",
    )
    orchestrator.record_manual_published(
        post.id,
        Platform.FACEBOOK,
        remote_post_id="fb-123",
        permalink_url="https://www.facebook.com/post",
    )
    assert repository.get_post(post.id).status is PostStatus.COMPLETED


def test_automatic_tiktok_result_is_recorded_without_manual_confirmation(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )
    tiktok = FakeAutomaticTikTok()
    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=tiktok,
        facebook_factory=lambda _checkpoint=None: FakeFacebook(),
        secret_store=FakeSecrets(),
    )

    result = orchestrator.prepare_tiktok(post.id)

    delivery = repository.get_delivery_for_platform(post.id, Platform.TIKTOK)
    assert result.platform_result is not None
    assert result.platform_result.state == STATE_SCHEDULED
    assert delivery.status is DeliveryStatus.SCHEDULED
    assert delivery.remote_upload_id == "tiktok-scheduled-123"


def test_tiktok_login_required_before_upload_remains_retryable(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )
    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=FakeLoginRequiredTikTok(),
        secret_store=EmptySecrets(),
    )

    result = orchestrator.prepare_tiktok(post.id)

    delivery = repository.get_delivery_for_platform(post.id, Platform.TIKTOK)
    assert delivery.status is DeliveryStatus.RETRY_WAIT
    assert "bấm Đăng TikTok lại" in result.message


def test_facebook_can_be_scheduled_while_tiktok_is_still_pending(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )
    facebook = FakeFacebook()

    def facebook_factory(checkpoint=None):
        facebook.checkpoint = checkpoint
        return facebook

    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=FakeTikTok(),
        facebook_factory=facebook_factory,
        secret_store=FakeSecrets(),
    )

    orchestrator.schedule_facebook(post.id)

    assert len(facebook.publish_calls) == 1
    assert (
        repository.get_delivery_for_platform(post.id, Platform.FACEBOOK).status
        is DeliveryStatus.SCHEDULED
    )
    assert (
        repository.get_delivery_for_platform(post.id, Platform.TIKTOK).status
        is DeliveryStatus.PENDING
    )


def test_default_facebook_upload_uses_browser_without_page_token(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )

    calls = []

    class FakeBrowserFacebook:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def publish(self, request):
            calls.append(("publish", request))
            return PublishResult(
                state=STATE_AWAITING_CONFIRMATION,
                metadata={"video_uploaded": True},
                message="Đã đưa video vào Chrome.",
            )

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.FacebookBrowserPublisher",
        FakeBrowserFacebook,
    )
    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=FakeTikTok(),
        secret_store=EmptySecrets(),
    )

    result = orchestrator.schedule_facebook(post.id)

    delivery = repository.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    assert result.platform_result is not None
    assert delivery.status is DeliveryStatus.AWAITING_CONFIRMATION
    assert any(call[0] == "publish" for call in calls)


def test_default_publishers_use_exactly_one_shared_browser_factory(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path / "db.sqlite3")
    orchestrator = PublishingOrchestrator(
        repository, _config(tmp_path), secret_store=EmptySecrets()
    )

    facebook = orchestrator._facebook_upload_publisher()

    assert orchestrator.tiktok._session_factory is orchestrator.shared_browser_sessions
    assert facebook._session_factory is orchestrator.shared_browser_sessions
    assert facebook._close_session_on_close is False


def test_tiktok_login_button_never_attaches_playwright(tmp_path: Path) -> None:
    class LoginSafeTikTok(FakeTikTok):
        def check_connection(self):
            raise AssertionError("Playwright must not attach during login")

    repository = Repository(tmp_path / "db.sqlite3")
    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=LoginSafeTikTok(),
        secret_store=EmptySecrets(),
    )
    expected = BrowserConnectionResult(False, "Hãy đăng nhập trong Chrome.")
    orchestrator.chrome_login.open_tiktok = lambda: expected

    result = orchestrator.verify_tiktok_connection()

    assert result is expected


def test_v053_browser_start_failure_is_safely_unlocked_on_startup(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    delivery = repository.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repository.claim_delivery(delivery.id, "v053")
    token = claimed.lease_token or ""
    repository.mark_preparing(delivery.id, token)
    repository.mark_needs_action(
        delivery.id,
        token,
        error_code="FACEBOOK_BROWSER_START_FAILED",
        error_message="Playwright Sync API inside the asyncio loop",
    )

    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=FakeTikTok(),
        secret_store=EmptySecrets(),
    )

    recovered = repository.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    assert orchestrator.recovered_browser_failures == 1
    assert recovered.status is DeliveryStatus.PENDING
    assert recovered.last_error_code is None


def test_retryable_facebook_browser_failure_returns_to_retry_wait(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )

    class RetryableFacebook(FakeFacebook):
        def publish(self, request):
            self.publish_calls.append(request)
            raise PublisherError(
                "FACEBOOK_BROWSER_START_FAILED",
                "Không gắn được Chrome.",
                retryable=True,
            )

    facebook = RetryableFacebook()
    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=FakeTikTok(),
        facebook_factory=lambda _checkpoint=None: facebook,
        secret_store=EmptySecrets(),
    )

    with pytest.raises(OrchestrationError, match="bấm Đăng FB lại"):
        orchestrator.schedule_facebook(post.id)

    delivery = repository.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    assert delivery.status is DeliveryStatus.RETRY_WAIT


def test_changed_tiktok_account_is_blocked_before_tiktok_upload(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    tiktok = FakeTikTok()
    changed_config = replace(_config(tmp_path), tiktok_account_id="@other_account")
    orchestrator = PublishingOrchestrator(
        repository,
        changed_config,
        tiktok=tiktok,
        facebook_factory=lambda _checkpoint=None: FakeFacebook(),
        secret_store=FakeSecrets(),
    )

    with pytest.raises(OrchestrationError, match="Tài khoản TikTok hiện tại khác"):
        orchestrator.prepare_tiktok(post.id)

    assert tiktok.calls == []


def test_unknown_facebook_outcome_keeps_checkpoint_and_cannot_requeue(
    monkeypatch, tmp_path: Path
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"dummy-video")
    repository = Repository(tmp_path / "db.sqlite3")
    post = repository.create_post(
        video_path=str(video),
        video_sha256=sha256_file(video),
        caption="Nội dung",
        hashtags="#TKV",
    )
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=2),
        destinations={
            Platform.FACEBOOK: "123456",
            Platform.TIKTOK: "@test_account",
        },
    )
    monkeypatch.setattr(
        "mxh_publisher.services.orchestrator.run_dry_run",
        lambda **_kwargs: DryRunReport((CheckResult(True, "OK", "OK"),)),
    )

    class UnknownFacebook(FakeFacebook):
        def publish(self, request):
            self.publish_calls.append(request)
            assert self.checkpoint is not None
            self.checkpoint(
                PublishCheckpoint(
                    platform="facebook",
                    post_id=request.post_id,
                    stage="upload_initialized",
                    remote_id="vid-unknown",
                )
            )
            raise PublisherError(
                "facebook.finish_unknown",
                "Kết quả chưa rõ.",
                retryable=False,
                unknown_outcome=True,
                metadata={"video_id": "vid-unknown"},
            )

    facebook = UnknownFacebook()

    def facebook_factory(checkpoint=None):
        facebook.checkpoint = checkpoint
        return facebook

    orchestrator = PublishingOrchestrator(
        repository,
        _config(tmp_path),
        tiktok=FakeTikTok(),
        facebook_factory=facebook_factory,
        secret_store=FakeSecrets(),
    )
    orchestrator.prepare_tiktok(post.id)
    with pytest.raises(OrchestrationError):
        orchestrator.confirm_tiktok_and_schedule_facebook(post.id)

    delivery = repository.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    assert delivery.status is DeliveryStatus.UNKNOWN
    assert delivery.remote_upload_id == "vid-unknown"
    with pytest.raises(InvalidStateError):
        repository.requeue_delivery(delivery.id, confirmed_no_remote=True)
