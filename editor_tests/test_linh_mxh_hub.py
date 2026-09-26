from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from mxh_publisher.models import Platform
from mxh_publisher.repository import Repository
from mxh_publisher.services.linh_mxh_hub import (
    DualStreamRequest,
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
