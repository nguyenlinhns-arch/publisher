from datetime import datetime

from mxh_publisher.services.tiktok_verification import verify_content_text


def test_requires_both_title_and_exact_local_minute() -> None:
    scheduled = datetime(2026, 7, 12, 19, 30)
    result = verify_content_text(
        "Video tuyển thợ mỏ 12/07/2026 19:30 Scheduled",
        title="Video tuyển thợ mỏ",
        scheduled_local=scheduled,
    )
    assert result.matched
    assert result.confidence == "high"


def test_partial_match_never_passes() -> None:
    result = verify_content_text(
        "Video tuyển thợ mỏ Scheduled",
        title="Video tuyển thợ mỏ",
        scheduled_local=datetime(2026, 7, 12, 19, 30),
    )
    assert not result.matched
