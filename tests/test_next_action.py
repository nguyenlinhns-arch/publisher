from datetime import UTC, datetime, timedelta

from mxh_publisher.models import Platform
from mxh_publisher.repository import Repository
from mxh_publisher.services.next_action import next_action


def test_next_action_progression(tmp_path) -> None:
    repository = Repository(":memory:")
    assert next_action(repository, None).key == "save"
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    post = repository.create_post(video_path=str(video), caption="caption")
    assert next_action(repository, post.id).key == "approve"
    repository.approve_post(post.id)
    repository.schedule_post(
        post.id,
        datetime.now(UTC) + timedelta(hours=4),
        destinations={Platform.FACEBOOK: "123", Platform.TIKTOK: "@test"},
    )
    assert next_action(repository, post.id).key == "prepare_tiktok"
