from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mxh_publisher.db import Database, SCHEMA_VERSION
from mxh_publisher.models import (
    AttemptStatus,
    DeliveryStatus,
    InvalidStateError,
    LeaseConflictError,
    Platform,
    PostStatus,
    ValidationError,
)
from mxh_publisher.repository import Repository


UTC = timezone.utc
BASE_TIME = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository(tmp_path / "publisher.sqlite3")


def make_video(tmp_path: Path, name: str = "video.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"small deterministic test video")
    return path


def create_ready_post(
    repo: Repository,
    tmp_path: Path,
    *,
    platforms: tuple[Platform, ...] = (Platform.FACEBOOK,),
):
    video = make_video(tmp_path)
    post = repo.create_post(
        video_path=str(video),
        title="Test",
        caption="Caption chung",
        hashtags=("#TKV", "#ViecLam"),
        now=BASE_TIME,
    )
    repo.set_destinations(post.id, platforms, now=BASE_TIME)
    return repo.approve_post(post.id, now=BASE_TIME)


def test_database_initialization_is_idempotent_and_versioned(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "publisher.sqlite3")
    database.initialize()
    database.initialize()

    assert database.schema_version() == SCHEMA_VERSION
    with database.connection() as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        migrations = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert {"posts", "deliveries", "attempts", "settings"} <= tables
    assert [row["version"] for row in migrations] == list(range(1, SCHEMA_VERSION + 1))


def test_unique_destination_and_content_change_revokes_approval(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    assert post.status is PostStatus.READY
    assert post.is_approved

    first = repo.ensure_delivery(post.id, Platform.FACEBOOK, now=BASE_TIME)
    second = repo.ensure_delivery(post.id, Platform.FACEBOOK, now=BASE_TIME)
    assert first.id == second.id
    assert len(repo.list_deliveries(post_id=post.id)) == 1

    scheduled = repo.schedule_post(
        post.id, BASE_TIME + timedelta(hours=2), now=BASE_TIME
    )
    assert scheduled.status is PostStatus.SCHEDULED

    title_only = repo.update_post(
        post.id, title="Tên nội bộ mới", now=BASE_TIME + timedelta(minutes=1)
    )
    assert title_only.is_approved
    assert title_only.scheduled_at is not None

    changed = repo.update_post(
        post.id,
        caption="Caption đã sửa",
        now=BASE_TIME + timedelta(minutes=2),
    )
    assert changed.status is PostStatus.DRAFT
    assert not changed.is_approved
    assert changed.scheduled_at is None
    delivery = repo.get_delivery(first.id)
    assert delivery.status is DeliveryStatus.PENDING
    assert delivery.next_attempt_at is None


def test_schedule_requires_approval(repo: Repository, tmp_path: Path) -> None:
    video = make_video(tmp_path)
    post = repo.create_post(video_path=str(video), now=BASE_TIME)
    repo.ensure_delivery(post.id, Platform.FACEBOOK, now=BASE_TIME)

    with pytest.raises(InvalidStateError):
        repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)


def test_cross_post_duplicate_schedule_is_blocked(
    repo: Repository, tmp_path: Path
) -> None:
    video = make_video(tmp_path)
    posts = []
    for _ in range(2):
        post = repo.create_post(
            video_path=str(video),
            caption="Caption chung",
            hashtags=("#TKV", "#ViecLam"),
            now=BASE_TIME,
        )
        repo.set_destinations(post.id, (Platform.FACEBOOK,), now=BASE_TIME)
        posts.append(repo.approve_post(post.id, now=BASE_TIME))
    first, second = posts
    due = BASE_TIME + timedelta(hours=2)

    repo.schedule_post(first.id, due, now=BASE_TIME)

    with pytest.raises(InvalidStateError, match="lịch đăng trùng"):
        repo.schedule_post(second.id, due, now=BASE_TIME)


def test_manual_resolution_requires_safe_state_and_matching_url(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=2), now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)

    with pytest.raises(InvalidStateError):
        repo.resolve_as_published(
            delivery.id,
            remote_post_id="remote-post",
            confirmed_by="operator",
            now=BASE_TIME,
        )

    claimed = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)
    with pytest.raises(LeaseConflictError):
        repo.resolve_as_published(
            delivery.id,
            remote_post_id="remote-post",
            confirmed_by="operator",
            now=BASE_TIME,
        )
    repo.mark_preparing(delivery.id, claimed.lease_token, now=BASE_TIME)
    repo.mark_scheduled(
        delivery.id,
        claimed.lease_token,
        remote_upload_id="video-id",
        next_check_at=BASE_TIME + timedelta(hours=2),
        now=BASE_TIME,
    )

    with pytest.raises(ValidationError, match="không thuộc facebook"):
        repo.resolve_as_published(
            delivery.id,
            remote_post_id="remote-post",
            url="https://attacker.example/post",
            confirmed_by="operator",
            now=BASE_TIME + timedelta(minutes=1),
        )


def test_manual_preparation_remote_schedule_and_due_polling(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    publish_at = BASE_TIME + timedelta(hours=2)
    repo.schedule_post(post.id, publish_at, now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)

    # A pending item is deliberately not auto-uploaded when its time arrives.
    assert repo.claim_due_delivery("timer", now=publish_at) is None

    claimed = repo.claim_delivery(delivery.id, "preparer", now=BASE_TIME)
    assert claimed.lease_token
    with pytest.raises(LeaseConflictError):
        repo.claim_delivery(delivery.id, "second-worker", now=BASE_TIME)

    attempt = repo.begin_attempt(
        delivery.id, claimed.lease_token, phase="prepare", now=BASE_TIME
    )
    preparing = repo.mark_preparing(delivery.id, claimed.lease_token, now=BASE_TIME)
    uploading = repo.mark_uploading(
        delivery.id,
        preparing.lease_token,
        remote_upload_id="upload-1",
        now=BASE_TIME,
    )
    remote_scheduled = repo.mark_scheduled(
        delivery.id,
        uploading.lease_token,
        remote_post_id="post-1",
        next_check_at=publish_at,
        now=BASE_TIME,
    )
    repo.finish_attempt(attempt.id, AttemptStatus.SUCCEEDED, now=BASE_TIME)

    assert remote_scheduled.status is DeliveryStatus.SCHEDULED
    assert remote_scheduled.lease_token is None
    assert (
        repo.claim_due_delivery("timer", now=publish_at - timedelta(seconds=1)) is None
    )

    poll_claim = repo.claim_due_delivery("timer", now=publish_at)
    assert poll_claim is not None
    poll = repo.begin_attempt(
        delivery.id, poll_claim.lease_token, phase="verify", now=publish_at
    )
    processing = repo.mark_processing(
        delivery.id,
        poll_claim.lease_token,
        next_check_at=publish_at + timedelta(seconds=30),
        now=publish_at,
    )
    repo.finish_attempt(poll.id, AttemptStatus.SUCCEEDED, now=publish_at)
    assert processing.status is DeliveryStatus.PROCESSING

    final_time = publish_at + timedelta(seconds=30)
    final_claim = repo.claim_due_delivery("timer", now=final_time)
    assert final_claim is not None
    final_poll = repo.begin_attempt(
        delivery.id, final_claim.lease_token, phase="verify", now=final_time
    )
    published = repo.mark_published(
        delivery.id,
        final_claim.lease_token,
        remote_post_id="post-1",
        remote_url="https://www.facebook.com/post-1",
        now=final_time,
    )
    repo.finish_attempt(final_poll.id, AttemptStatus.SUCCEEDED, now=final_time)

    assert published.status is DeliveryStatus.PUBLISHED
    assert repo.get_post(post.id).status is PostStatus.COMPLETED


def test_confirmation_processing_and_unknown_are_non_duplicate_states(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path, platforms=(Platform.TIKTOK,))
    publish_at = BASE_TIME + timedelta(hours=1)
    repo.schedule_post(post.id, publish_at, now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.TIKTOK)

    claimed = repo.claim_delivery(delivery.id, "prepare", now=BASE_TIME)
    repo.mark_preparing(delivery.id, claimed.lease_token, now=BASE_TIME)
    uploading = repo.mark_uploading(
        delivery.id,
        claimed.lease_token,
        remote_upload_id="tt-upload",
        now=BASE_TIME,
    )
    awaiting = repo.mark_awaiting_confirmation(
        delivery.id,
        uploading.lease_token,
        next_check_at=BASE_TIME + timedelta(minutes=5),
        now=BASE_TIME,
    )
    assert awaiting.status is DeliveryStatus.AWAITING_CONFIRMATION
    assert awaiting.lease_token is None

    poll_time = BASE_TIME + timedelta(minutes=5)
    poll_claim = repo.claim_due_delivery("poll", now=poll_time)
    assert poll_claim is not None
    processing = repo.mark_processing(
        delivery.id,
        poll_claim.lease_token,
        next_check_at=poll_time + timedelta(minutes=1),
        now=poll_time,
    )
    assert processing.status is DeliveryStatus.PROCESSING
    assert processing.lease_token is None

    next_poll = repo.claim_due_delivery("poll", now=poll_time + timedelta(minutes=1))
    unknown = repo.mark_unknown(
        delivery.id,
        next_poll.lease_token,
        error_message="Mất kết nối sau khi hỏi trạng thái",
        now=poll_time + timedelta(minutes=1),
    )
    assert unknown.status is DeliveryStatus.UNKNOWN
    assert unknown.lease_token is None
    reconcile = repo.claim_due_delivery(
        "poll", now=poll_time + timedelta(hours=1)
    )
    assert reconcile is not None
    assert reconcile.status is DeliveryStatus.UNKNOWN
    assert reconcile.remote_upload_id == "tt-upload"
    repo.mark_processing(
        reconcile.id,
        reconcile.lease_token,
        remote_upload_id="tt-upload",
        next_check_at=poll_time + timedelta(hours=1, minutes=15),
        now=poll_time + timedelta(hours=1),
    )


def test_expired_upload_lease_requires_human_review(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(
        delivery.id, "worker", now=BASE_TIME, lease_seconds=10
    )
    repo.mark_uploading(delivery.id, claimed.lease_token, now=BASE_TIME)

    recovered = repo.recover_expired_leases(now=BASE_TIME + timedelta(seconds=11))
    current = repo.get_delivery(delivery.id)

    assert recovered == 1
    assert current.status is DeliveryStatus.NEEDS_ACTION
    assert current.last_error_code == "lease_expired_unknown_outcome"
    assert current.lease_token is None


def test_attempts_and_json_settings(repo: Repository, tmp_path: Path) -> None:
    post = create_ready_post(repo, tmp_path)
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)

    attempt = repo.begin_attempt(
        delivery.id,
        claimed.lease_token,
        details={"mode": "dry-run"},
        now=BASE_TIME,
    )
    finished = repo.finish_attempt(
        attempt.id,
        AttemptStatus.FAILED,
        retryable=True,
        error_code="network",
        details={"status": 503},
        now=BASE_TIME + timedelta(seconds=1),
    )
    assert finished.attempt_no == 1
    assert finished.retryable is True
    assert finished.details == {"status": 503}
    assert repo.get_delivery(delivery.id).attempt_count == 1

    repo.set_setting("ui.theme", {"name": "light"}, now=BASE_TIME)
    assert repo.get_setting("ui.theme") == {"name": "light"}
    assert repo.get_setting("missing", "fallback") == "fallback"
    assert repo.delete_setting("ui.theme") is True
    assert repo.delete_setting("ui.theme") is False


def test_remote_checkpoint_survives_unknown_and_keeps_lease(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)

    checkpoint = repo.checkpoint_remote_id(
        delivery.id,
        claimed.lease_token,
        remote_upload_id="upload-checkpoint",
        now=BASE_TIME,
    )
    assert checkpoint.remote_upload_id == "upload-checkpoint"
    assert checkpoint.lease_token == claimed.lease_token

    with pytest.raises(InvalidStateError):
        repo.checkpoint_remote_id(
            delivery.id,
            claimed.lease_token,
            remote_upload_id="different-upload",
            now=BASE_TIME,
        )

    unknown = repo.mark_unknown(
        delivery.id,
        claimed.lease_token,
        remote_upload_id="upload-checkpoint",
        remote_post_id="remote-post",
        now=BASE_TIME,
    )
    assert unknown.status is DeliveryStatus.UNKNOWN
    assert unknown.remote_upload_id == "upload-checkpoint"
    assert unknown.remote_post_id == "remote-post"
    assert unknown.lease_token is None


def test_requeue_requires_confirmation_and_never_accepts_remote_ids(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)
    attempt = repo.begin_attempt(delivery.id, claimed.lease_token, now=BASE_TIME)
    repo.finish_attempt(
        attempt.id,
        AttemptStatus.FAILED,
        error_code="local_failure",
        now=BASE_TIME,
    )
    repo.mark_failed(
        delivery.id,
        claimed.lease_token,
        error_code="local_failure",
        error_message="No request was sent",
        now=BASE_TIME,
    )

    with pytest.raises(InvalidStateError):
        repo.requeue_delivery(delivery.id, now=BASE_TIME)
    requeued = repo.requeue_delivery(
        delivery.id, confirmed_no_remote=True, now=BASE_TIME
    )
    assert requeued.status is DeliveryStatus.PENDING

    claimed_again = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)
    repo.checkpoint_remote_id(
        delivery.id,
        claimed_again.lease_token,
        remote_upload_id="remote-upload",
        now=BASE_TIME,
    )
    repo.mark_needs_action(
        delivery.id,
        claimed_again.lease_token,
        error_code="verify",
        error_message="Check remotely",
        remote_upload_id="remote-upload",
        remote_post_id="possible-post",
        now=BASE_TIME,
    )
    risky = repo.get_delivery(delivery.id)
    assert risky.remote_upload_id == "remote-upload"
    assert risky.remote_post_id == "possible-post"
    with pytest.raises(InvalidStateError):
        repo.requeue_delivery(delivery.id, confirmed_no_remote=True, now=BASE_TIME)


def test_cancelled_history_cannot_be_revived(repo: Repository, tmp_path: Path) -> None:
    post = create_ready_post(
        repo, tmp_path, platforms=(Platform.FACEBOOK, Platform.TIKTOK)
    )
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    tiktok = repo.get_delivery_for_platform(post.id, Platform.TIKTOK)
    claimed = repo.claim_delivery(tiktok.id, "worker", now=BASE_TIME)
    attempt = repo.begin_attempt(tiktok.id, claimed.lease_token, now=BASE_TIME)
    repo.finish_attempt(
        attempt.id, AttemptStatus.FAILED, error_code="local", now=BASE_TIME
    )
    repo.mark_failed(
        tiktok.id,
        claimed.lease_token,
        error_code="local",
        error_message="No remote call",
        now=BASE_TIME,
    )
    repo.set_destinations(post.id, (Platform.FACEBOOK,), now=BASE_TIME)
    assert repo.get_delivery(tiktok.id).status is DeliveryStatus.CANCELLED

    with pytest.raises(InvalidStateError):
        repo.ensure_delivery(post.id, Platform.TIKTOK, now=BASE_TIME)
    with pytest.raises(InvalidStateError):
        repo.set_destinations(
            post.id, (Platform.FACEBOOK, Platform.TIKTOK), now=BASE_TIME
        )


def test_manual_resolution_records_audit_and_is_idempotent(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)
    repo.mark_unknown(
        delivery.id,
        claimed.lease_token,
        remote_post_id="verified-post",
        now=BASE_TIME,
    )

    resolved = repo.resolve_as_published(
        delivery.id,
        remote_post_id="verified-post",
        url="https://www.facebook.com/verified-post",
        confirmed_by="teacher-linh",
        now=BASE_TIME + timedelta(minutes=1),
    )
    attempts = repo.list_attempts(delivery_id=delivery.id)
    assert resolved.status is DeliveryStatus.PUBLISHED
    assert resolved.remote_post_id == "verified-post"
    assert attempts[0].phase == "manual_resolution"
    assert attempts[0].details["confirmed_by"] == "teacher-linh"
    assert repo.get_post(post.id).status is PostStatus.COMPLETED

    again = repo.resolve_as_published(
        delivery.id,
        remote_post_id="verified-post",
        url="https://www.facebook.com/verified-post",
        confirmed_by="teacher-linh",
        now=BASE_TIME + timedelta(minutes=2),
    )
    assert again.status is DeliveryStatus.PUBLISHED
    assert len(repo.list_attempts(delivery_id=delivery.id)) == len(attempts)


def test_approve_is_idempotent_and_blocked_after_remote_work(
    repo: Repository, tmp_path: Path
) -> None:
    post = create_ready_post(repo, tmp_path)
    same = repo.approve_post(post.id, now=BASE_TIME + timedelta(minutes=1))
    assert same.approved_at == post.approved_at
    assert same.updated_at == post.updated_at

    repo.schedule_post(post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    still_scheduled = repo.approve_post(post.id, now=BASE_TIME + timedelta(minutes=2))
    assert still_scheduled.status is PostStatus.SCHEDULED

    delivery = repo.get_delivery_for_platform(post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(delivery.id, "worker", now=BASE_TIME)
    repo.mark_preparing(delivery.id, claimed.lease_token, now=BASE_TIME)
    with pytest.raises(InvalidStateError):
        repo.approve_post(post.id, now=BASE_TIME + timedelta(minutes=3))


def test_schedule_never_resets_failed_or_retry_wait(
    repo: Repository, tmp_path: Path
) -> None:
    failed_post = create_ready_post(repo, tmp_path, platforms=(Platform.FACEBOOK,))
    original_due = BASE_TIME + timedelta(hours=1)
    repo.schedule_post(failed_post.id, original_due, now=BASE_TIME)
    failed_delivery = repo.get_delivery_for_platform(failed_post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(failed_delivery.id, "worker", now=BASE_TIME)
    repo.checkpoint_remote_id(
        failed_delivery.id,
        claimed.lease_token,
        remote_upload_id="uncertain-upload",
        now=BASE_TIME,
    )
    repo.mark_failed(
        failed_delivery.id,
        claimed.lease_token,
        error_code="transport_error",
        error_message="Outcome requires review",
        now=BASE_TIME,
    )

    with pytest.raises(InvalidStateError):
        repo.schedule_post(
            failed_post.id, BASE_TIME + timedelta(hours=2), now=BASE_TIME
        )
    unchanged = repo.get_delivery(failed_delivery.id)
    assert unchanged.status is DeliveryStatus.FAILED
    assert unchanged.remote_upload_id == "uncertain-upload"
    assert unchanged.last_error_code == "transport_error"
    assert repo.get_post(failed_post.id).scheduled_at == original_due

    retry_video = make_video(tmp_path, "retry.mp4")
    retry_post = repo.create_post(video_path=str(retry_video), now=BASE_TIME)
    repo.ensure_delivery(retry_post.id, Platform.TIKTOK, now=BASE_TIME)
    repo.approve_post(retry_post.id, now=BASE_TIME)
    repo.schedule_post(retry_post.id, original_due, now=BASE_TIME)
    retry_delivery = repo.get_delivery_for_platform(retry_post.id, Platform.TIKTOK)
    retry_claim = repo.claim_delivery(retry_delivery.id, "worker", now=BASE_TIME)
    repo.mark_retry_wait(
        retry_delivery.id,
        retry_claim.lease_token,
        next_attempt_at=BASE_TIME + timedelta(minutes=5),
        error_code="local_retry",
        error_message="No remote request was made",
        now=BASE_TIME,
    )
    with pytest.raises(InvalidStateError):
        repo.schedule_post(retry_post.id, BASE_TIME + timedelta(hours=2), now=BASE_TIME)
    assert repo.get_delivery(retry_delivery.id).status is DeliveryStatus.RETRY_WAIT

    repo.requeue_delivery(retry_delivery.id, now=BASE_TIME)
    rescheduled = repo.schedule_post(
        retry_post.id, BASE_TIME + timedelta(hours=2), now=BASE_TIME
    )
    assert rescheduled.status is PostStatus.SCHEDULED


def test_mutation_claim_rejects_remote_evidence_but_verify_claim_allows_it(
    repo: Repository, tmp_path: Path
) -> None:
    unsafe_post = create_ready_post(repo, tmp_path, platforms=(Platform.FACEBOOK,))
    repo.schedule_post(unsafe_post.id, BASE_TIME + timedelta(hours=1), now=BASE_TIME)
    unsafe = repo.get_delivery_for_platform(unsafe_post.id, Platform.FACEBOOK)
    claimed = repo.claim_delivery(unsafe.id, "worker", now=BASE_TIME)
    repo.checkpoint_remote_id(
        unsafe.id,
        claimed.lease_token,
        remote_upload_id="already-created-upload",
        now=BASE_TIME,
    )
    repo.release_lease(unsafe.id, claimed.lease_token, now=BASE_TIME)
    with pytest.raises(InvalidStateError):
        repo.claim_delivery(unsafe.id, "mutation-worker", now=BASE_TIME)

    verify_video = make_video(tmp_path, "verify.mp4")
    verify_post = repo.create_post(video_path=str(verify_video), now=BASE_TIME)
    repo.ensure_delivery(verify_post.id, Platform.FACEBOOK, now=BASE_TIME)
    repo.approve_post(verify_post.id, now=BASE_TIME)
    due = BASE_TIME + timedelta(hours=1)
    repo.schedule_post(verify_post.id, due, now=BASE_TIME)
    verify = repo.get_delivery_for_platform(verify_post.id, Platform.FACEBOOK)
    prepare = repo.claim_delivery(verify.id, "prepare", now=BASE_TIME)
    repo.mark_preparing(verify.id, prepare.lease_token, now=BASE_TIME)
    repo.mark_uploading(
        verify.id,
        prepare.lease_token,
        remote_upload_id="verified-upload",
        now=BASE_TIME,
    )
    repo.mark_scheduled(
        verify.id,
        prepare.lease_token,
        remote_upload_id="verified-upload",
        remote_post_id="scheduled-post",
        next_check_at=due,
        now=BASE_TIME,
    )

    scheduled_claim = repo.claim_delivery(verify.id, "verify-worker", now=BASE_TIME)
    assert scheduled_claim.status is DeliveryStatus.SCHEDULED
    assert scheduled_claim.remote_post_id == "scheduled-post"
    repo.mark_processing(
        verify.id,
        scheduled_claim.lease_token,
        remote_upload_id="verified-upload",
        next_check_at=due,
        now=BASE_TIME,
    )
    processing_claim = repo.claim_delivery(verify.id, "verify-worker", now=BASE_TIME)
    assert processing_claim.status is DeliveryStatus.PROCESSING
    assert processing_claim.remote_upload_id == "verified-upload"
