from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect
from pathlib import Path
from typing import Sequence

import pytest

from mxh_publisher.publishers.base import PublishRequest, PublisherError
from mxh_publisher.publishers import tiktok as tiktok_module
from mxh_publisher.publishers.tiktok import (
    CAPTION_INPUT_SELECTORS,
    PREVIEW_READY_SELECTORS,
    STATE_AUTHENTICATION_REQUIRED,
    STATE_AWAITING_CONFIRMATION,
    STATE_MANUAL_ACTION_REQUIRED,
    STATE_VERIFICATION_REQUIRED,
    TikTokPublisher,
    UPLOAD_INPUT_SELECTORS,
)


class FakeBrowserSession:
    def __init__(
        self,
        *,
        visible_selectors: set[str] | None = None,
        body_text: str = "TikTok Studio",
        current_url: str = "https://www.tiktok.com/tiktokstudio/upload",
        body_text_after_upload: str | None = None,
        upload_error: Exception | None = None,
        fill_error: Exception | None = None,
    ) -> None:
        self.visible_selectors = set(visible_selectors or set())
        self._body_text = body_text
        self._body_text_after_upload = body_text_after_upload
        self._url = current_url
        self.upload_error = upload_error
        self.fill_error = fill_error
        self.operations: list[tuple[object, ...]] = []
        self.closed = False

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, *, timeout_ms: int) -> None:
        self.operations.append(("goto", url, timeout_ms))
        # Tests can preconfigure a redirect URL (login, for example).  A normal
        # fake follows the requested upload URL.
        if "/login" not in self._url and "/signin" not in self._url:
            self._url = url

    def body_text(self) -> str:
        self.operations.append(("body_text",))
        return self._body_text

    def first_present(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        self.operations.append(("first_present", tuple(selectors), timeout_ms))
        return next(
            (selector for selector in selectors if selector in self.visible_selectors),
            None,
        )

    def first_visible(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        self.operations.append(("first_visible", tuple(selectors), timeout_ms))
        return next(
            (selector for selector in selectors if selector in self.visible_selectors),
            None,
        )

    def set_input_files(self, selector: str, path: Path) -> None:
        self.operations.append(("set_input_files", selector, path))
        if self.upload_error is not None:
            raise self.upload_error
        if self._body_text_after_upload is not None:
            self._body_text = self._body_text_after_upload

    def fill(self, selector: str, value: str) -> None:
        self.operations.append(("fill", selector, value))
        if self.fill_error is not None:
            raise self.fill_error

    def wait(self, milliseconds: int) -> None:
        self.operations.append(("wait", milliseconds))

    def screenshot(self, path: Path) -> None:
        self.operations.append(("screenshot", path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")

    def close(self) -> None:
        self.operations.append(("close",))
        self.closed = True

    def click(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("TikTok assisted adapter must never click")


class FakeSessionFactory:
    def __init__(self, session: FakeBrowserSession) -> None:
        self.session = session
        self.calls: list[tuple[Path, str, bool]] = []

    def __call__(
        self, profile_dir: Path, browser_channel: str, headless: bool
    ) -> FakeBrowserSession:
        self.calls.append((profile_dir, browser_channel, headless))
        return self.session


def _request(video_path: Path, *, caption: str = "Caption #NghềMỏ") -> PublishRequest:
    return PublishRequest(
        post_id=42,
        video_path=video_path,
        caption=caption,
        scheduled_at_utc=datetime.now(UTC) + timedelta(hours=2),
        options={},
    )


def _publisher(
    tmp_path: Path, session: FakeBrowserSession
) -> tuple[TikTokPublisher, FakeSessionFactory]:
    factory = FakeSessionFactory(session)
    publisher = TikTokPublisher(
        browser_profile_dir=tmp_path / "browser-profile",
        screenshots_dir=tmp_path / "screenshots",
        session_factory=factory,
        control_timeout_ms=0,
        preview_timeout_ms=0,
        upload_settle_ms=0,
    )
    return publisher, factory


def test_prepare_uploads_and_fills_but_never_submits(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={
            UPLOAD_INPUT_SELECTORS[0],
            CAPTION_INPUT_SELECTORS[0],
            PREVIEW_READY_SELECTORS[0],
        },
        current_url="https://www.tiktok.com/tiktokstudio/upload?token=do-not-log",
    )
    publisher, factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_AWAITING_CONFIRMATION
    assert result.remote_id is None
    assert result.permalink_url is None
    assert result.metadata["video_uploaded"] is True
    assert result.metadata["caption_filled"] is True
    assert result.metadata["preview_detected"] is True
    assert result.metadata["publish_action_performed"] is False
    assert result.metadata["schedule_action_performed"] is False
    assert result.metadata["confirmation_required"] is True
    assert "?" not in result.metadata["current_url"]
    assert Path(str(result.metadata["screenshot_path"])).is_file()

    assert factory.calls == [(tmp_path / "browser-profile", "msedge", False)]
    operation_names = [str(operation[0]) for operation in session.operations]
    assert "set_input_files" in operation_names
    assert "fill" in operation_names
    assert "click" not in operation_names
    fill_operation = next(op for op in session.operations if op[0] == "fill")
    assert fill_operation[2] == "Caption #NghềMỏ"


@pytest.mark.parametrize(
    ("page_text", "expected_kind"),
    [
        ("Verify to continue — CAPTCHA", "captcha"),
        ("Vui lòng nhập mã xác minh gồm 6 chữ số", "two_factor"),
    ],
)
def test_captcha_and_two_factor_stop_before_upload(
    tmp_path: Path, page_text: str, expected_kind: str
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0]}, body_text=page_text
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_VERIFICATION_REQUIRED
    assert result.metadata["challenge"] == expected_kind
    assert result.metadata["phase"] == "before_upload"
    assert result.metadata["publish_action_performed"] is False
    assert Path(str(result.metadata["screenshot_path"])).is_file()
    assert not any(
        operation[0] == "set_input_files" for operation in session.operations
    )


def test_two_factor_appearing_after_upload_stops_immediately(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={
            UPLOAD_INPUT_SELECTORS[0],
            CAPTION_INPUT_SELECTORS[0],
        },
        body_text_after_upload="Enter verification code",
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_VERIFICATION_REQUIRED
    assert result.metadata["challenge"] == "two_factor"
    assert result.metadata["phase"] == "after_upload"
    assert any(operation[0] == "set_input_files" for operation in session.operations)
    assert not any(operation[0] == "fill" for operation in session.operations)


def test_login_redirect_requires_manual_authentication(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        current_url="https://www.tiktok.com/login?redirect_url=secret",
        body_text="Log in to TikTok",
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_AUTHENTICATION_REQUIRED
    assert result.metadata["challenge"] == "login"
    assert result.metadata["current_url"] == "https://www.tiktok.com/login"
    assert not any(
        operation[0] == "set_input_files" for operation in session.operations
    )


def test_missing_caption_control_remains_safe_for_manual_completion(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={
            UPLOAD_INPUT_SELECTORS[0],
            PREVIEW_READY_SELECTORS[0],
        }
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_AWAITING_CONFIRMATION
    assert result.metadata["caption_control_found"] is False
    assert result.metadata["caption_filled"] is False
    assert "điền thủ công" in result.message
    assert not any(operation[0] == "fill" for operation in session.operations)


def test_caption_fill_error_does_not_risk_submission(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={
            UPLOAD_INPUT_SELECTORS[0],
            CAPTION_INPUT_SELECTORS[0],
            PREVIEW_READY_SELECTORS[0],
        },
        fill_error=RuntimeError("editor changed"),
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_AWAITING_CONFIRMATION
    assert result.metadata["caption_filled"] is False
    assert result.metadata["caption_fill_error"] == "editor changed"
    assert result.metadata["publish_action_performed"] is False


def test_preview_absent_returns_manual_action_instead_of_awaiting_confirmation(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={
            UPLOAD_INPUT_SELECTORS[0],
            CAPTION_INPUT_SELECTORS[0],
        }
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_MANUAL_ACTION_REQUIRED
    assert result.state != STATE_AWAITING_CONFIRMATION
    assert result.metadata["reason"] == "preview_not_ready"
    assert result.metadata["video_uploaded"] is True
    assert result.metadata["caption_filled"] is True
    assert result.metadata["preview_detected"] is False
    assert result.metadata["publish_action_performed"] is False
    assert result.metadata["schedule_action_performed"] is False
    assert Path(str(result.metadata["screenshot_path"])).is_file()
    assert not any(operation[0] == "click" for operation in session.operations)


def test_missing_upload_control_returns_maintainable_manual_state(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(visible_selectors=set())
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(_request(video))

    assert result.state == STATE_MANUAL_ACTION_REQUIRED
    assert result.metadata["reason"] == "upload_control_not_found"
    assert Path(str(result.metadata["screenshot_path"])).is_file()
    assert not any(
        operation[0] == "set_input_files" for operation in session.operations
    )


def test_missing_video_raises_structured_error_without_starting_browser(
    tmp_path: Path,
) -> None:
    session = FakeBrowserSession()
    publisher, factory = _publisher(tmp_path, session)

    with pytest.raises(PublisherError) as captured:
        publisher.publish(_request(tmp_path / "missing.mp4"))

    assert captured.value.code == "TIKTOK_VIDEO_NOT_FOUND"
    assert captured.value.retryable is False
    assert captured.value.unknown_outcome is False
    assert factory.calls == []


def test_upload_error_is_structured_and_known_not_to_have_submitted(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0]},
        upload_error=RuntimeError("file chooser failed"),
    )
    publisher, _factory = _publisher(tmp_path, session)

    with pytest.raises(PublisherError) as captured:
        publisher.publish(_request(video))

    error = captured.value
    assert error.code == "TIKTOK_UPLOAD_FAILED"
    assert error.retryable is True
    assert error.unknown_outcome is False
    assert error.metadata["publish_action_performed"] is False
    assert Path(str(error.metadata["screenshot_path"])).is_file()


def test_browser_profile_inside_repository_is_rejected(tmp_path: Path) -> None:
    del tmp_path
    project_root = Path(tiktok_module.__file__).resolve().parents[3]

    with pytest.raises(ValueError, match="ngoài thư mục dự án"):
        TikTokPublisher(browser_profile_dir=project_root / "unsafe-profile")


def test_close_is_explicit_and_session_is_reusable(tmp_path: Path) -> None:
    session = FakeBrowserSession()
    publisher, factory = _publisher(tmp_path, session)
    publisher._browser()
    publisher._browser()

    assert len(factory.calls) == 1
    publisher.close()
    assert session.closed is True


def test_adapter_source_contains_no_click_call() -> None:
    source = inspect.getsource(tiktok_module)
    assert ".click(" not in source
