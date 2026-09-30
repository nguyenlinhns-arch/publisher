from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from mxh_publisher.config import AppConfig
from mxh_publisher.models import DeliveryStatus, Platform
from mxh_publisher.repository import Repository
from mxh_publisher.services.linh_mxh_hub import (
    DualStreamRequest,
    OrchestratorDispatcher,
    RepositoryHubScheduler,
    StreamSpec,
    schedule_video_dual_stream,
)


TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")


def _video(tmp_path: Path, name: str, payload: bytes) -> tuple[Path, str]:
    path = tmp_path / name
    path.write_bytes(payload)
    return path, sha256(payload).hexdigest()


def _scheduled_post(
    repository: Repository,
    *,
    path: Path,
    digest: str,
    title: str,
    due: datetime,
    account_id: str,
    now: datetime,
):
    post = repository.create_post(
        video_path=str(path),
        video_sha256=digest,
        title=title,
        caption=title,
    )
    repository.approve_post(post.id, now=now)
    return repository.schedule_post(
        post.id,
        due,
        destinations={Platform.FACEBOOK: account_id},
        now=now,
    )


def test_dual_stream_finds_next_free_days_and_is_idempotent(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "publisher.sqlite3")
    now = datetime(2026, 9, 26, 7, 0, tzinfo=TZ)

    source_path, source_sha = _video(tmp_path, "source.mp4", b"source")
    repository.create_post(
        video_path=str(source_path),
        video_sha256=source_sha,
        title="Video chính xác",
        caption="Video chính xác",
    )

    busy_2_path, busy_2_sha = _video(tmp_path, "busy2.mp4", b"busy-2")
    _scheduled_post(
        repository,
        path=busy_2_path,
        digest=busy_2_sha,
        title="Bận luồng 2",
        due=datetime(2026, 9, 26, 9, 0, tzinfo=TZ),
        account_id="222",
        now=now,
    )

    busy_1_path, busy_1_sha = _video(tmp_path, "busy1.mp4", b"busy-1")
    _scheduled_post(
        repository,
        path=busy_1_path,
        digest=busy_1_sha,
        title="Bận luồng 1",
        due=datetime(2026, 9, 29, 9, 0, tzinfo=TZ),
        account_id="111",
        now=now,
    )

    request = DualStreamRequest(
        video_title="Video chính xác",
        stream_2=StreamSpec(
            "stream-2",
            {Platform.FACEBOOK.value: "222"},
        ),
        stream_1=StreamSpec(
            "stream-1",
            {Platform.FACEBOOK.value: "111"},
        ),
    )

    plan = RepositoryHubScheduler(repository, request, now=now).plan()
    assert plan.stream_2.scheduled_at == datetime(
        2026, 9, 27, 9, 0, tzinfo=TZ
    )
    assert plan.stream_1.scheduled_at == datetime(
        2026, 9, 30, 9, 0, tzinfo=TZ
    )

    first = schedule_video_dual_stream(repository, request, now=now)
    assert first.final_status == "PREPARED"
    assert first.stream_2_scheduled_at.startswith("2026-09-27T09:00:00")
    assert first.stream_1_scheduled_at.startswith("2026-09-30T09:00:00")

    second = schedule_video_dual_stream(repository, request, now=now)
    assert second.idempotency_key == first.idempotency_key
    assert second.stream_2_post_id == first.stream_2_post_id
    assert second.stream_1_post_id == first.stream_1_post_id

    source_clones = [
        post
        for post in repository.list_posts(search="Video chính xác", limit=1000)
        if post.title == "Video chính xác" and post.scheduled_at is not None
    ]
    assert len(source_clones) == 2


def test_dual_stream_never_schedules_inside_minimum_lead(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "publisher.sqlite3")
    now = datetime(2026, 9, 26, 8, 30, tzinfo=TZ)
    source_path, source_sha = _video(tmp_path, "source.mp4", b"source")
    repository.create_post(
        video_path=str(source_path),
        video_sha256=source_sha,
        title="Video 2",
        caption="Video 2",
    )
    request = DualStreamRequest(
        video_title="Video 2",
        stream_2=StreamSpec(
            "stream-2",
            {Platform.FACEBOOK.value: "222"},
        ),
        stream_1=StreamSpec(
            "stream-1",
            {Platform.FACEBOOK.value: "111"},
        ),
        minimum_lead_minutes=60,
    )

    plan = RepositoryHubScheduler(repository, request, now=now).plan()

    assert plan.stream_2.scheduled_at == datetime(
        2026, 9, 27, 9, 0, tzinfo=TZ
    )
    assert plan.stream_1.scheduled_at == datetime(
        2026, 9, 29, 9, 0, tzinfo=TZ
    )



class _ReceiptDispatcher:
    def __init__(self) -> None:
        self.dispatch_calls: list[tuple[str, str]] = []
        self.verified = False

    def __call__(self, post_id: str, stream: StreamSpec):
        self.dispatch_calls.append((post_id, stream.stream_id))
        return {
            "status": "SUBMITTED_UNVERIFIED",
            "deliveries": {"facebook": "processing"},
            "bridge": "video_publish_bridge",
            "executor": "mxh_video_tool",
        }

    def readback(self, post_id: str, stream: StreamSpec):
        if self.verified:
            return {
                "status": "SCHEDULED",
                "deliveries": {"facebook": "scheduled"},
                "bridge": "video_publish_bridge",
                "executor": "mxh_video_tool",
            }
        return {
            "status": "SUBMITTED_UNVERIFIED",
            "deliveries": {"facebook": "processing"},
            "bridge": "video_publish_bridge",
            "executor": "mxh_video_tool",
        }


def test_submitted_unverified_reconciles_without_duplicate_dispatch(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "publisher.sqlite3")
    now = datetime(2026, 9, 26, 7, 0, tzinfo=TZ)
    source_path, source_sha = _video(tmp_path, "source.mp4", b"receipt-source")
    repository.create_post(
        video_path=str(source_path),
        video_sha256=source_sha,
        title="Video receipt",
        caption="Video receipt",
    )
    request = DualStreamRequest(
        video_title="Video receipt",
        stream_2=StreamSpec(
            "stream-2",
            {Platform.FACEBOOK.value: "222"},
        ),
        stream_1=StreamSpec(
            "stream-1",
            {Platform.FACEBOOK.value: "111"},
        ),
    )
    dispatcher = _ReceiptDispatcher()

    first = schedule_video_dual_stream(
        repository,
        request,
        now=now,
        remote_dispatcher=dispatcher,
    )
    assert first.final_status == "SUBMITTED_UNVERIFIED"
    assert len(dispatcher.dispatch_calls) == 2

    dispatcher.verified = True
    second = schedule_video_dual_stream(
        repository,
        request,
        now=now,
        remote_dispatcher=dispatcher,
    )
    assert second.final_status == "DONE_EXISTING"
    assert len(dispatcher.dispatch_calls) == 2
    assert second.remote["stream_2"]["status"] == "SCHEDULED"
    assert second.remote["stream_1"]["status"] == "SCHEDULED"


def test_mxh_delivery_classifier_keeps_processing_non_retryable() -> None:
    classify = OrchestratorDispatcher._classify_delivery_states
    assert classify({"facebook": "processing"}) == "SUBMITTED_UNVERIFIED"
    assert classify({"facebook": "unknown"}) == "SUBMITTED_UNVERIFIED"
    assert classify({"facebook": "awaiting_confirmation"}) == "SUBMITTED_UNVERIFIED"
    assert classify({"facebook": "retry_wait"}) == "PREPARED"
    assert classify({"facebook": "failed"}) == "ERROR"
    assert classify({"facebook": "scheduled", "tiktok": "published"}) == "SCHEDULED"
    assert classify({"facebook": "scheduled", "tiktok": "pending"}) == "PREPARED"
    assert classify({"facebook": "scheduled", "tiktok": "retry_wait"}) == "PREPARED"
    assert (
        classify({"facebook": "scheduled", "tiktok": "processing"})
        == "SUBMITTED_UNVERIFIED"
    )

class _PartialRecoveryDispatcher:
    def __init__(self) -> None:
        self.dispatch_calls: list[tuple[str, str]] = []

    def readback(self, post_id: str, stream: StreamSpec):
        return {
            "status": "PREPARED",
            "deliveries": {
                "facebook": "scheduled",
                "tiktok": "pending",
            },
            "bridge": "video_publish_bridge",
            "executor": "mxh_video_tool",
        }

    def __call__(self, post_id: str, stream: StreamSpec):
        self.dispatch_calls.append((post_id, stream.stream_id))
        return {
            "status": "SCHEDULED",
            "deliveries": {
                "facebook": "scheduled",
                "tiktok": "scheduled",
            },
            "bridge": "video_publish_bridge",
            "executor": "mxh_video_tool",
        }


def test_existing_partial_stream_recovers_pending_platform(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "publisher.sqlite3")
    now = datetime(2026, 9, 26, 7, 0, tzinfo=TZ)
    source_path, source_sha = _video(tmp_path, "partial.mp4", b"partial-source")
    repository.create_post(
        video_path=str(source_path),
        video_sha256=source_sha,
        title="Video partial",
        caption="Video partial",
    )
    request = DualStreamRequest(
        video_title="Video partial",
        stream_2=StreamSpec(
            "stream-2",
            {
                Platform.FACEBOOK.value: "222",
                Platform.TIKTOK.value: "@stream2",
            },
        ),
        stream_1=StreamSpec(
            "stream-1",
            {
                Platform.FACEBOOK.value: "111",
                Platform.TIKTOK.value: "@stream1",
            },
        ),
    )

    prepared = schedule_video_dual_stream(repository, request, now=now)
    assert prepared.final_status == "PREPARED"

    dispatcher = _PartialRecoveryDispatcher()
    recovered = schedule_video_dual_stream(
        repository,
        request,
        now=now,
        remote_dispatcher=dispatcher,
    )

    assert recovered.final_status == "DONE_EXISTING"
    assert len(dispatcher.dispatch_calls) == 2


def test_dispatcher_isolates_platform_failures_and_skips_done_platform(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []

    class _FakeOrchestrationError(RuntimeError):
        pass

    class _RepoStub:
        def __init__(self) -> None:
            self.states = {
                Platform.TIKTOK: DeliveryStatus.PENDING,
                Platform.FACEBOOK: DeliveryStatus.PENDING,
            }

        def get_delivery_for_platform(self, post_id: str, platform: Platform):
            return SimpleNamespace(status=self.states[platform])

    repo = _RepoStub()

    class _FakeOrchestrator:
        def __init__(self, repository, config) -> None:
            self.repository = repository

        def prepare_tiktok(self, post_id: str):
            calls.append("tiktok")
            if calls.count("tiktok") == 1:
                self.repository.states[Platform.TIKTOK] = DeliveryStatus.RETRY_WAIT
                raise _FakeOrchestrationError("TikTok needs login")
            self.repository.states[Platform.TIKTOK] = DeliveryStatus.SCHEDULED
            return SimpleNamespace(message="TikTok scheduled")

        def schedule_facebook(self, post_id: str):
            calls.append("facebook")
            self.repository.states[Platform.FACEBOOK] = DeliveryStatus.SCHEDULED
            return SimpleNamespace(message="Facebook scheduled")

        def close(self) -> None:
            pass

    fake_module = ModuleType("mxh_publisher.services.orchestrator")
    fake_module.OrchestrationError = _FakeOrchestrationError
    fake_module.PublishingOrchestrator = _FakeOrchestrator
    monkeypatch.setitem(
        sys.modules,
        "mxh_publisher.services.orchestrator",
        fake_module,
    )

    config = AppConfig(
        root_dir=tmp_path,
        database_path=tmp_path / "publisher.sqlite3",
        media_dir=tmp_path / "media",
        logs_dir=tmp_path / "logs",
        screenshots_dir=tmp_path / "screenshots",
        browser_profile_dir=tmp_path / "browser_profile",
        facebook_page_id="222",
        tiktok_account_id="@stream2",
    )
    dispatcher = OrchestratorDispatcher(repo, config)
    stream = StreamSpec(
        "stream-2",
        {
            Platform.FACEBOOK.value: "222",
            Platform.TIKTOK.value: "@stream2",
        },
    )

    first = dispatcher("post-1", stream)
    assert first["status"] == "PREPARED"
    assert calls == ["tiktok", "facebook"]
    assert first["deliveries"] == {
        "facebook": "scheduled",
        "tiktok": "retry_wait",
    }

    second = dispatcher("post-1", stream)
    assert second["status"] == "SCHEDULED"
    assert calls == ["tiktok", "facebook", "tiktok"]
    assert second["deliveries"] == {
        "facebook": "scheduled",
        "tiktok": "scheduled",
    }

