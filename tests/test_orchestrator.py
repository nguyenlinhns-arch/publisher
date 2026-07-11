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
from mxh_publisher.publishers.tiktok import STATE_AWAITING_CONFIRMATION
from mxh_publisher.repository import InvalidStateError, Repository
from mxh_publisher.services.dry_run import CheckResult, DryRunReport
from mxh_publisher.services.media import sha256_file
from mxh_publisher.services.orchestrator import (
    OrchestrationError,
    PublishingOrchestrator,
)


class FakeSecrets:
    def get(self, _name: str) -> str:
        return "fake-token"


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


def test_changed_page_is_blocked_before_tiktok_upload(tmp_path: Path) -> None:
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
    changed_config = replace(_config(tmp_path), facebook_page_id="999999")
    orchestrator = PublishingOrchestrator(
        repository,
        changed_config,
        tiktok=tiktok,
        facebook_factory=lambda _checkpoint=None: FakeFacebook(),
        secret_store=FakeSecrets(),
    )

    with pytest.raises(OrchestrationError, match="khác Page đã khóa"):
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
