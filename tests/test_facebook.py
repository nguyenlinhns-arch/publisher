from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from mxh_publisher.publishers.base import (
    PublishCheckpoint,
    PublishCheckpointCallback,
    PublishRequest,
    PublisherError,
)
from mxh_publisher.publishers.facebook import FacebookPublisher


PAGE_ID = "123456"
TOKEN = "page-token-must-not-leak"
NOW = datetime(2026, 7, 10, 3, 0, tzinfo=timezone.utc)


def _form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.read().decode())


def _is_start(request: httpx.Request) -> bool:
    return _form(request).get("upload_phase") == ["start"]


def _request(tmp_path: Path, **overrides: object) -> PublishRequest:
    video_path = tmp_path / "reel.mp4"
    video_path.write_bytes(b"test-video-bytes")
    values: dict[str, object] = {
        "post_id": 42,
        "video_path": video_path,
        "caption": "A safe caption #TKV",
        "scheduled_at_utc": None,
        "options": {},
    }
    values.update(overrides)
    return PublishRequest(**values)  # type: ignore[arg-type]


def _publisher(
    handler: httpx.MockTransport,
    *,
    max_status_polls: int = 2,
    max_upload_attempts: int = 2,
    checkpoint_callback: PublishCheckpointCallback | None = None,
) -> FacebookPublisher:
    client = httpx.Client(transport=handler)
    return FacebookPublisher(
        page_id=PAGE_ID,
        token_provider=lambda: TOKEN,
        client=client,
        poll_interval_seconds=0,
        max_status_polls=max_status_polls,
        max_upload_attempts=max_upload_attempts,
        sleep=lambda _: None,
        clock=lambda: NOW,
        checkpoint_callback=checkpoint_callback,
    )


def _complete_status() -> dict[str, object]:
    return {
        "status": {
            "video_status": "ready",
            "uploading_phase": {"status": "complete"},
            "processing_phase": {"status": "complete"},
            "publishing_phase": {"status": "complete"},
        }
    }


def test_publishes_reel_and_verifies_permalink_without_token_in_url(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        assert TOKEN not in str(request.url)

        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                assert request.headers.get("content-type", "").startswith(
                    "application/x-www-form-urlencoded"
                )
                assert _form(request) == {"upload_phase": ["start"]}
                assert request.headers["authorization"] == f"Bearer {TOKEN}"
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9001",
                        "upload_url": "https://rupload.facebook.com/video-upload/9001",
                    },
                )
            form = _form(request)
            assert form["upload_phase"] == ["finish"]
            assert form["video_state"] == ["PUBLISHED"]
            assert form["video_id"] == ["9001"]
            assert form["description"] == ["A safe caption #TKV"]
            assert request.headers["authorization"] == f"Bearer {TOKEN}"
            return httpx.Response(
                200,
                json={"success": True, "video_id": "9001", "post_id": "123456_88"},
            )

        if request.url.host == "rupload.facebook.com":
            assert request.headers["authorization"] == f"OAuth {TOKEN}"
            assert request.headers["offset"] == "0"
            assert request.read() == b"test-video-bytes"
            return httpx.Response(200, json={"success": True})

        if request.url.path == "/v25.0/9001":
            assert request.url.params["fields"] == "status"
            return httpx.Response(200, json=_complete_status())

        if request.url.path == "/v25.0/123456_88":
            assert request.url.params["fields"] == (
                "is_published,permalink_url,created_time"
            )
            return httpx.Response(
                200,
                json={
                    "is_published": True,
                    "permalink_url": "https://www.facebook.com/reel/9001",
                    "created_time": "2026-07-10T03:00:00+0000",
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(httpx.MockTransport(handler))
    result = publisher.publish(_request(tmp_path))

    assert result.state == "published"
    assert result.remote_id == "123456_88"
    assert result.permalink_url == "https://www.facebook.com/reel/9001"
    assert result.metadata["video_id"] == "9001"
    assert calls == [
        f"POST /v25.0/{PAGE_ID}/video_reels",
        "POST /video-upload/9001",
        f"POST /v25.0/{PAGE_ID}/video_reels",
        "GET /v25.0/9001",
        "GET /v25.0/123456_88",
    ]


def test_checkpoints_video_id_immediately_before_upload(tmp_path: Path) -> None:
    events: list[str] = []
    checkpoints: list[PublishCheckpoint] = []

    def checkpoint_callback(checkpoint: PublishCheckpoint) -> None:
        assert events == ["start_returned"]
        checkpoints.append(checkpoint)
        events.append("checkpoint_saved")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                events.append("start_returned")
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9010",
                        "upload_url": "https://rupload.facebook.com/video-upload/9010",
                    },
                )
            assert events == ["start_returned", "checkpoint_saved", "upload"]
            events.append("finish")
            return httpx.Response(200, json={"success": True})
        if request.url.host == "rupload.facebook.com":
            assert events == ["start_returned", "checkpoint_saved"]
            events.append("upload")
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/v25.0/9010":
            return httpx.Response(200, json=_complete_status())
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(
        httpx.MockTransport(handler), checkpoint_callback=checkpoint_callback
    )
    result = publisher.publish(_request(tmp_path))

    assert result.state == "published"
    assert events == ["start_returned", "checkpoint_saved", "upload", "finish"]
    assert checkpoints == [
        PublishCheckpoint(
            platform="facebook",
            post_id=42,
            stage="upload_initialized",
            remote_id="9010",
            metadata={"video_id": "9010", "page_id": PAGE_ID},
        )
    ]


def test_checkpoint_failure_stops_before_upload_and_preserves_video_id(
    tmp_path: Path,
) -> None:
    network_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        network_paths.append(request.url.path)
        assert request.url.path == f"/v25.0/{PAGE_ID}/video_reels"
        assert _is_start(request)
        return httpx.Response(
            200,
            json={
                "video_id": "9011",
                "upload_url": "https://rupload.facebook.com/video-upload/9011",
            },
        )

    def fail_checkpoint(_checkpoint: PublishCheckpoint) -> None:
        raise OSError("SQLite is unavailable")

    publisher = _publisher(
        httpx.MockTransport(handler), checkpoint_callback=fail_checkpoint
    )
    with pytest.raises(PublisherError) as caught:
        publisher.publish(_request(tmp_path))

    error = caught.value
    assert error.code == "facebook.checkpoint_failed"
    assert error.retryable is False
    assert error.unknown_outcome is False
    assert error.metadata["video_id"] == "9011"
    assert error.metadata["required_action"] == "save_checkpoint_before_resume"
    assert network_paths == [f"/v25.0/{PAGE_ID}/video_reels"]


def test_graph_error_after_start_always_carries_checkpointed_video_id(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            assert _is_start(request)
            return httpx.Response(
                200,
                json={
                    "video_id": "9012",
                    "upload_url": "https://rupload.facebook.com/video-upload/9012",
                },
            )
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Unsupported video parameters",
                        "code": 100,
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(httpx.MockTransport(handler))
    with pytest.raises(PublisherError) as caught:
        publisher.publish(_request(tmp_path))

    assert caught.value.code == "facebook.invalid_request"
    assert caught.value.metadata["video_id"] == "9012"
    assert caught.value.metadata["stage"] == "upload"


def test_schedules_reel_with_epoch_and_title(tmp_path: Path) -> None:
    scheduled_at = NOW + timedelta(hours=1)
    observed_finish: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9002",
                        "upload_url": "https://rupload.facebook.com/video-upload/9002",
                    },
                )
            observed_finish.update(_form(request))
            return httpx.Response(200, json={"success": True})
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/v25.0/9002":
            return httpx.Response(
                200,
                json={
                    "status": {
                        "video_status": "ready",
                        "uploading_phase": {"status": "complete"},
                        "processing_phase": {"status": "complete"},
                        "publishing_phase": {"status": "not_started"},
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(httpx.MockTransport(handler))
    result = publisher.publish(
        _request(
            tmp_path,
            scheduled_at_utc=scheduled_at,
            options={"facebook_title": "Reel title"},
        )
    )

    assert result.state == "scheduled"
    assert result.remote_id == "9002"
    assert observed_finish["video_state"] == ["SCHEDULED"]
    assert observed_finish["scheduled_publish_time"] == [
        str(int(scheduled_at.timestamp()))
    ]
    assert observed_finish["title"] == ["Reel title"]


def test_graph_auth_error_is_structured_and_redacts_token(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": f"Invalid token {TOKEN}",
                    "type": "OAuthException",
                    "code": 190,
                    "error_subcode": 463,
                    "fbtrace_id": "trace-1",
                }
            },
        )

    publisher = _publisher(httpx.MockTransport(handler))
    with pytest.raises(PublisherError) as caught:
        publisher.publish(_request(tmp_path))

    error = caught.value
    assert error.code == "facebook.auth_required"
    assert error.retryable is False
    assert error.unknown_outcome is False
    assert TOKEN not in str(error)
    assert error.metadata["graph_code"] == 190
    assert error.metadata["graph_subcode"] == 463


def test_interrupted_upload_resumes_from_reported_offset(tmp_path: Path) -> None:
    video = tmp_path / "resume.mp4"
    video.write_bytes(b"abcdefghij")
    upload_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upload_attempts
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9003",
                        "upload_url": "https://rupload.facebook.com/video-upload/9003",
                    },
                )
            return httpx.Response(200, json={"success": True})
        if request.url.host == "rupload.facebook.com":
            upload_attempts += 1
            body = request.read()
            if upload_attempts == 1:
                assert request.headers["offset"] == "0"
                assert body == b"abcdefghij"
                raise httpx.WriteError("connection interrupted", request=request)
            assert request.headers["offset"] == "4"
            assert request.headers["file_size"] == "10"
            assert body == b"efghij"
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/v25.0/9003":
            # First GET reconciles upload progress; the second verifies publish.
            if upload_attempts == 1:
                return httpx.Response(
                    200,
                    json={
                        "status": {
                            "video_status": "processing",
                            "uploading_phase": {
                                "status": "in_progress",
                                "bytes_transfered": 4,
                            },
                            "processing_phase": {"status": "not_started"},
                            "publishing_phase": {"status": "not_started"},
                        }
                    },
                )
            return httpx.Response(200, json=_complete_status())
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(httpx.MockTransport(handler))
    result = publisher.publish(_request(tmp_path, video_path=video))

    assert result.state == "published"
    assert upload_attempts == 2


def test_finish_timeout_is_reconciled_without_second_finish(tmp_path: Path) -> None:
    finish_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal finish_calls
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9004",
                        "upload_url": "https://rupload.facebook.com/video-upload/9004",
                    },
                )
            finish_calls += 1
            raise httpx.ReadTimeout("response was lost", request=request)
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/v25.0/9004":
            return httpx.Response(200, json=_complete_status())
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(httpx.MockTransport(handler))
    result = publisher.publish(_request(tmp_path))

    assert result.state == "published"
    assert result.remote_id == "9004"
    assert result.metadata["reconciled_after_ambiguous_finish"] is True
    assert finish_calls == 1


def test_finish_timeout_with_inconclusive_status_marks_unknown_outcome(
    tmp_path: Path,
) -> None:
    finish_calls = 0
    status_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal finish_calls, status_calls
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9005",
                        "upload_url": "https://rupload.facebook.com/video-upload/9005",
                    },
                )
            finish_calls += 1
            raise httpx.ReadTimeout("response was lost", request=request)
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/v25.0/9005":
            status_calls += 1
            return httpx.Response(
                200,
                json={
                    "status": {
                        "video_status": "processing",
                        "uploading_phase": {"status": "complete"},
                        "processing_phase": {"status": "in_progress"},
                        "publishing_phase": {"status": "not_started"},
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(
        httpx.MockTransport(handler),
        max_status_polls=3,
    )
    with pytest.raises(PublisherError) as caught:
        publisher.publish(_request(tmp_path))

    error = caught.value
    assert error.code == "facebook.finish_unknown"
    assert error.unknown_outcome is True
    assert error.retryable is False
    assert error.metadata["video_id"] == "9005"
    assert error.metadata["required_action"] == "verify_before_retry"
    assert finish_calls == 1
    assert status_calls == 3


def test_processing_error_is_not_reported_as_published(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v25.0/{PAGE_ID}/video_reels":
            if _is_start(request):
                return httpx.Response(
                    200,
                    json={
                        "video_id": "9006",
                        "upload_url": "https://rupload.facebook.com/video-upload/9006",
                    },
                )
            return httpx.Response(200, json={"success": True})
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/v25.0/9006":
            return httpx.Response(
                200,
                json={
                    "status": {
                        "video_status": "error",
                        "uploading_phase": {"status": "complete"},
                        "processing_phase": {
                            "status": "error",
                            "error": {"message": "Resolution too low"},
                        },
                        "publishing_phase": {"status": "not_started"},
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    publisher = _publisher(httpx.MockTransport(handler))
    with pytest.raises(PublisherError) as caught:
        publisher.publish(_request(tmp_path))

    assert caught.value.code == "facebook.processing_failed"
    assert caught.value.retryable is False
    assert "Resolution too low" in str(caught.value)


def test_rejects_schedule_too_close_without_fetching_token(tmp_path: Path) -> None:
    token_calls = 0

    def token_provider() -> str:
        nonlocal token_calls
        token_calls += 1
        return TOKEN

    publisher = FacebookPublisher(
        page_id=PAGE_ID,
        token_provider=token_provider,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    AssertionError(f"Network should not be called: {request.url}")
                )
            )
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(PublisherError) as caught:
        publisher.publish(
            _request(tmp_path, scheduled_at_utc=NOW + timedelta(minutes=5))
        )

    assert caught.value.code == "facebook.invalid_schedule"
    assert token_calls == 0
