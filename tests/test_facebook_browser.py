from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

import pytest

from mxh_publisher.publishers.base import PublishRequest, PublisherError
from mxh_publisher.publishers.facebook_browser import (
    CAPTION_INPUT_SELECTORS,
    STATE_AWAITING_CONFIRMATION,
    UPLOAD_INPUT_SELECTORS,
    FacebookBrowserPublisher,
)


class FakeBrowser:
    def __init__(
        self,
        *,
        current_url: str = "https://business.facebook.com/latest/reels_composer?asset_id=123456",
        body: str = "Create reel",
        selectors: set[str] | None = None,
    ) -> None:
        self._url = current_url
        self.body = body
        self.selectors = selectors or set()
        self.operations: list[tuple[object, ...]] = []
        self.closed = False

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, *, timeout_ms: int) -> None:
        self.operations.append(("goto", url, timeout_ms))
        if "/login" not in self._url:
            self._url = url

    def body_text(self) -> str:
        return self.body

    def first_present(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        self.operations.append(("first_present", timeout_ms))
        return next((item for item in selectors if item in self.selectors), None)

    def first_visible(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        self.operations.append(("first_visible", timeout_ms))
        return next((item for item in selectors if item in self.selectors), None)

    def set_input_files(self, selector: str, path: Path) -> None:
        self.operations.append(("set_input_files", selector, path))

    def fill(self, selector: str, value: str) -> None:
        self.operations.append(("fill", selector, value))

    def wait(self, milliseconds: int) -> None:
        self.operations.append(("wait", milliseconds))

    def screenshot(self, path: Path) -> None:
        del path

    def click(self, selector: str) -> None:
        del selector

    def close(self) -> None:
        self.closed = True


def _request(video: Path, *, expected_hash: str | None = None) -> PublishRequest:
    return PublishRequest(
        post_id="post-1",
        video_path=video,
        caption="Nội dung\n\n#TKV",
        options={"video_sha256": expected_hash or hashlib.sha256(video.read_bytes()).hexdigest()},
    )


def _publisher(tmp_path: Path, session: FakeBrowser) -> FacebookBrowserPublisher:
    return FacebookBrowserPublisher(
        page_id="123456",
        browser_profile_dir=tmp_path / "profile",
        session_factory=lambda *_args: session,
        upload_settle_ms=1,
    )


def test_uploads_exact_edited_file_and_fills_caption(tmp_path: Path) -> None:
    video = tmp_path / "edited.mp4"
    video.write_bytes(b"edited-video")
    session = FakeBrowser(
        selectors={UPLOAD_INPUT_SELECTORS[0], CAPTION_INPUT_SELECTORS[0]}
    )

    result = _publisher(tmp_path, session).publish(_request(video))

    assert result.state == STATE_AWAITING_CONFIRMATION
    assert ("set_input_files", UPLOAD_INPUT_SELECTORS[0], video.resolve()) in session.operations
    assert ("fill", CAPTION_INPUT_SELECTORS[0], "Nội dung\n\n#TKV") in session.operations
    assert result.metadata["publish_action_performed"] is False


def test_login_redirect_stops_before_upload(tmp_path: Path) -> None:
    video = tmp_path / "edited.mp4"
    video.write_bytes(b"edited-video")
    session = FakeBrowser(
        current_url="https://www.facebook.com/login/",
        body="Đăng nhập vào Facebook",
        selectors={UPLOAD_INPUT_SELECTORS[0]},
    )

    with pytest.raises(PublisherError, match="chưa sẵn sàng"):
        _publisher(tmp_path, session).publish(_request(video))

    assert not any(operation[0] == "set_input_files" for operation in session.operations)


def test_changed_video_is_blocked_before_browser_mutation(tmp_path: Path) -> None:
    video = tmp_path / "edited.mp4"
    video.write_bytes(b"edited-video")
    session = FakeBrowser(selectors={UPLOAD_INPUT_SELECTORS[0]})

    with pytest.raises(PublisherError, match="đã sửa đổi"):
        _publisher(tmp_path, session).publish(_request(video, expected_hash="0" * 64))

    assert session.operations == []


def test_shared_session_is_not_closed_by_short_lived_facebook_adapter(
    tmp_path: Path,
) -> None:
    session = FakeBrowser(selectors={UPLOAD_INPUT_SELECTORS[0]})
    publisher = FacebookBrowserPublisher(
        page_id="123456",
        browser_profile_dir=tmp_path / "profile",
        session_factory=lambda *_args: session,
        close_session_on_close=False,
    )
    publisher._browser()

    publisher.close()

    assert session.closed is False
