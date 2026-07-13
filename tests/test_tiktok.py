from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import inspect
import os
from pathlib import Path
import sys
import types
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
        navigation_result_url: str | None = None,
        url_after_first_present: str | None = None,
    ) -> None:
        self.visible_selectors = set(visible_selectors or set())
        self._body_text = body_text
        self._body_text_after_upload = body_text_after_upload
        self._url = current_url
        self.upload_error = upload_error
        self.fill_error = fill_error
        self.navigation_result_url = navigation_result_url
        self.url_after_first_present = url_after_first_present
        self.operations: list[tuple[object, ...]] = []
        self.closed = False

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, *, timeout_ms: int) -> None:
        self.operations.append(("goto", url, timeout_ms))
        # Tests can preconfigure a redirect URL (login, for example).  A normal
        # fake follows the requested upload URL.
        if self.navigation_result_url is not None:
            self._url = self.navigation_result_url
        elif "/login" not in self._url and "/signin" not in self._url:
            self._url = url

    def body_text(self) -> str:
        self.operations.append(("body_text",))
        return self._body_text

    def first_present(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        self.operations.append(("first_present", tuple(selectors), timeout_ms))
        if self.url_after_first_present is not None:
            self._url = self.url_after_first_present
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
        if self._body_text_after_upload is not None:
            self._body_text = self._body_text_after_upload
        if self.upload_error is not None:
            raise self.upload_error

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


def _request(
    video_path: Path,
    *,
    caption: str = "Caption #NghềMỏ",
    options: dict[str, object] | None = None,
) -> PublishRequest:
    return PublishRequest(
        post_id=42,
        video_path=video_path,
        caption=caption,
        scheduled_at_utc=datetime.now(UTC) + timedelta(hours=2),
        options=options or {},
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


def test_connection_check_confirms_active_studio_session(tmp_path: Path) -> None:
    session = FakeBrowserSession(visible_selectors={UPLOAD_INPUT_SELECTORS[0]})
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.check_connection()

    assert result.connected
    assert "sẵn sàng" in result.message
    assert not any(operation[0] == "set_input_files" for operation in session.operations)
    assert not any(operation[0] == "click" for operation in session.operations)


def test_connection_check_opens_login_without_bypassing_it(tmp_path: Path) -> None:
    session = FakeBrowserSession(
        current_url="https://www.tiktok.com/login",
        body_text="Log in to TikTok",
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.check_connection()

    assert not result.connected
    assert "đăng nhập" in result.message.casefold()
    assert not any(operation[0] == "set_input_files" for operation in session.operations)
    assert not any(operation[0] == "click" for operation in session.operations)


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
    assert result.metadata["screenshot_path"] is None
    assert result.metadata["screenshot_skipped_reason"] == (
        "sensitive_authentication_challenge"
    )
    assert not any(operation[0] == "screenshot" for operation in session.operations)
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
    assert result.metadata["screenshot_path"] is None
    assert not any(operation[0] == "screenshot" for operation in session.operations)
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
    assert result.metadata["screenshot_path"] is None
    assert not any(operation[0] == "screenshot" for operation in session.operations)
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
    assert "@" not in str(captured.value.metadata.get("current_url", ""))
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


def test_upload_error_does_not_capture_a_new_authentication_challenge(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0]},
        body_text_after_upload="Enter the 6-digit code",
        upload_error=RuntimeError("page changed"),
    )
    publisher, _factory = _publisher(tmp_path, session)

    with pytest.raises(PublisherError) as captured:
        publisher.publish(_request(video))

    error = captured.value
    assert error.code == "TIKTOK_UPLOAD_FAILED"
    assert error.metadata["screenshot_path"] is None
    assert error.metadata["screenshot_error"] == (
        "screenshot_skipped_sensitive_authentication_challenge"
    )
    assert not any(operation[0] == "screenshot" for operation in session.operations)


@pytest.mark.parametrize(
    "upload_url",
    [
        "http://www.tiktok.com/tiktokstudio/upload",
        "https://tiktok.com/tiktokstudio/upload",
        "https://www.tiktok.com:443/tiktokstudio/upload",
        "https://user@www.tiktok.com/tiktokstudio/upload",
        "https://www.tiktok.com/tiktokstudio/upload/",
        "https://www.tiktok.com/tiktokstudio/content",
        "https://www.tiktok.com/tiktokstudio/upload?next=1",
        "https://www.tiktok.com/tiktokstudio/upload#fragment",
    ],
)
def test_configured_upload_url_must_be_exact_and_trusted(
    tmp_path: Path, upload_url: str
) -> None:
    with pytest.raises(ValueError, match="chính xác"):
        TikTokPublisher(
            browser_profile_dir=tmp_path / "browser-profile",
            screenshots_dir=tmp_path / "screenshots",
            upload_url=upload_url,
            session_factory=FakeSessionFactory(FakeBrowserSession()),
        )


@pytest.mark.parametrize(
    "redirect_url",
    [
        "https://attacker.example/tiktokstudio/upload",
        "http://www.tiktok.com/tiktokstudio/upload",
        "https://www.tiktok.com/profile",
        "https://user@www.tiktok.com/tiktokstudio/upload",
        "https://www.tiktok.com:443/tiktokstudio/upload",
    ],
)
def test_navigation_must_remain_on_trusted_tiktok_studio_before_file_selection(
    tmp_path: Path, redirect_url: str
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0]},
        navigation_result_url=redirect_url,
    )
    publisher, _factory = _publisher(tmp_path, session)

    with pytest.raises(PublisherError) as captured:
        publisher.publish(_request(video))

    assert captured.value.code == "TIKTOK_UNTRUSTED_PAGE"
    assert captured.value.retryable is False
    assert captured.value.unknown_outcome is False
    assert not any(
        operation[0] == "set_input_files" for operation in session.operations
    )
    assert not any(operation[0] == "screenshot" for operation in session.operations)


def test_navigation_is_rechecked_immediately_before_file_selection(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0]},
        url_after_first_present="https://attacker.example/tiktokstudio/upload",
    )
    publisher, _factory = _publisher(tmp_path, session)

    with pytest.raises(PublisherError) as captured:
        publisher.publish(_request(video))

    assert captured.value.code == "TIKTOK_UNTRUSTED_PAGE"
    assert not any(
        operation[0] == "set_input_files" for operation in session.operations
    )


def test_video_hash_is_rechecked_immediately_before_upload(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"approved-video")
    expected = hashlib.sha256(video.read_bytes()).hexdigest()
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0], PREVIEW_READY_SELECTORS[0]}
    )
    publisher, _factory = _publisher(tmp_path, session)

    result = publisher.publish(
        _request(video, options={"video_sha256": expected.upper()})
    )

    assert result.state == STATE_AWAITING_CONFIRMATION
    assert any(operation[0] == "set_input_files" for operation in session.operations)


def test_changed_video_is_blocked_before_file_selection(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"changed-video")
    session = FakeBrowserSession(visible_selectors={UPLOAD_INPUT_SELECTORS[0]})
    publisher, _factory = _publisher(tmp_path, session)

    with pytest.raises(PublisherError) as captured:
        publisher.publish(_request(video, options={"video_sha256": "0" * 64}))

    assert captured.value.code == "TIKTOK_VIDEO_CHANGED"
    assert captured.value.retryable is False
    assert captured.value.unknown_outcome is False
    assert not any(
        operation[0] == "set_input_files" for operation in session.operations
    )


def test_capture_removes_only_expired_tiktok_screenshots(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()
    expired = screenshots / "tiktok_old.png"
    fresh = screenshots / "tiktok_fresh.png"
    unrelated = screenshots / "other_old.png"
    for path in (expired, fresh, unrelated):
        path.write_bytes(b"png")
    now = datetime.now(UTC).timestamp()
    os.utime(expired, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))
    os.utime(fresh, (now - 6 * 24 * 60 * 60, now - 6 * 24 * 60 * 60))
    os.utime(unrelated, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))
    session = FakeBrowserSession(
        visible_selectors={UPLOAD_INPUT_SELECTORS[0], PREVIEW_READY_SELECTORS[0]}
    )
    publisher, _factory = _publisher(tmp_path, session)

    publisher.publish(_request(video))

    assert not expired.exists()
    assert fresh.exists()
    assert unrelated.exists()


class _FakeContext:
    def __init__(self) -> None:
        self.pages = [object()]
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _FakeChromium:
    def __init__(self, *, context: _FakeContext | None = None) -> None:
        self.context = context
        self.calls: list[dict[str, object]] = []

    def launch_persistent_context(self, _profile: str, **kwargs: object):
        self.calls.append(kwargs)
        if self.context is None:
            raise RuntimeError("channel missing")
        return self.context


class _FakePlaywrightManager:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, manager) -> None:
    module = types.ModuleType("playwright.sync_api")

    class _Starter:
        def start(self):
            return manager

    module.sync_playwright = lambda: _Starter()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)


def test_required_browser_channel_has_no_chromium_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chromium = _FakeChromium()
    manager = _FakePlaywrightManager(chromium)
    _install_fake_playwright(monkeypatch, manager)

    with pytest.raises(RuntimeError, match="kênh trình duyệt bắt buộc msedge"):
        tiktok_module._PlaywrightBrowserSession(
            tmp_path / "profile", "msedge", False
        )

    assert len(chromium.calls) == 1
    assert chromium.calls[0]["channel"] == "msedge"
    assert manager.stop_calls == 1


def test_browser_session_close_stops_manager_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _FakeContext()
    chromium = _FakeChromium(context=context)
    manager = _FakePlaywrightManager(chromium)
    _install_fake_playwright(monkeypatch, manager)
    session = tiktok_module._PlaywrightBrowserSession(
        tmp_path / "profile", "msedge", False
    )

    session.close()
    session.close()

    assert context.close_calls == 1
    assert manager.stop_calls == 1


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


def test_shared_browser_factory_reuses_one_session_for_both_platforms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeBrowserSession()
    starts: list[tuple[Path, str, bool]] = []

    def start(profile: Path, channel: str, headless: bool):
        starts.append((profile, channel, headless))
        return session

    monkeypatch.setattr(tiktok_module, "start_playwright_session", start)
    factory = tiktok_module.SharedBrowserSessionFactory()
    profile = tmp_path / "shared-profile"

    facebook_session = factory(profile, "msedge", False)
    tiktok_session = factory(profile, "msedge", False)

    assert facebook_session is session
    assert tiktok_session is session
    assert starts == [(profile.resolve(), "msedge", False)]


def test_adapter_source_contains_no_click_call() -> None:
    source = inspect.getsource(tiktok_module)
    assert ".click(" not in source
