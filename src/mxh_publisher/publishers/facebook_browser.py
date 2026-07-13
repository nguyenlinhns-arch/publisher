"""Facebook Page upload through the same visible Chrome used for TikTok.

This adapter intentionally prepares the Reel in Meta Business Suite and leaves
the final publish/schedule confirmation visible to the operator.  Browser UI is
less stable than Graph API, so the adapter only performs the deterministic
steps: navigate to the locked Page, select the exact edited file, and fill the
caption.  Repeated clicks are blocked by the delivery state in the orchestrator.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, urlencode, urlsplit

from .base import PublishRequest, PublishResult, PublisherError
from .tiktok import BrowserSession, BrowserSessionFactory, start_playwright_session


STATE_AWAITING_CONFIRMATION = "awaiting_confirmation"

UPLOAD_INPUT_SELECTORS: tuple[str, ...] = (
    'input[type="file"][accept*="video"]',
    'input[type="file"][accept*="mp4"]',
    'input[type="file"]',
)

CAPTION_INPUT_SELECTORS: tuple[str, ...] = (
    '[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"]',
    'textarea[placeholder*="caption" i]',
    'textarea[placeholder*="mô tả" i]',
    "textarea",
)

LOGIN_MARKERS: tuple[str, ...] = (
    "log into facebook",
    "log in to facebook",
    "đăng nhập facebook",
    "đăng nhập vào facebook",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _business_suite_url(page_id: str) -> str:
    if not page_id.isdigit():
        raise ValueError("Facebook Page ID phải là số.")
    return "https://business.facebook.com/latest/reels_composer?" + urlencode(
        {"asset_id": page_id}
    )


def _is_trusted_composer_url(value: str, page_id: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or parts.hostname not in {"business.facebook.com", "www.facebook.com"}
        or parts.username is not None
        or parts.password is not None
        or parts.port is not None
    ):
        return False
    if parts.hostname == "business.facebook.com":
        asset_ids = parse_qs(parts.query).get("asset_id", [])
        return parts.path.rstrip("/") == "/latest/reels_composer" and (
            not asset_ids or page_id in asset_ids
        )
    # Some Meta flows keep the composer under facebook.com after authentication.
    return not any(marker in parts.path.casefold() for marker in ("login", "checkpoint"))


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    folded = " ".join(text.casefold().split())
    return any(marker in folded for marker in markers)


class FacebookBrowserPublisher:
    """Upload an edited video to a locked Fanpage via visible Chrome."""

    platform = "facebook"

    def __init__(
        self,
        *,
        page_id: str,
        browser_profile_dir: Path,
        browser_channel: str = "chrome",
        session_factory: BrowserSessionFactory | None = None,
        navigation_timeout_ms: int = 45_000,
        control_timeout_ms: int = 20_000,
        upload_settle_ms: int = 2_000,
    ) -> None:
        self.page_id = page_id.strip()
        self.browser_profile_dir = browser_profile_dir.expanduser().resolve()
        self.browser_channel = browser_channel
        self._session_factory = session_factory or start_playwright_session
        self.navigation_timeout_ms = navigation_timeout_ms
        self.control_timeout_ms = control_timeout_ms
        self.upload_settle_ms = upload_settle_ms
        self._session: BrowserSession | None = None

    def _browser(self) -> BrowserSession:
        if self._session is None:
            try:
                self._session = self._session_factory(
                    self.browser_profile_dir, self.browser_channel, False
                )
            except Exception as exc:
                raise PublisherError(
                    "FACEBOOK_BROWSER_START_FAILED",
                    f"Không gắn được vào Chrome dùng chung: {exc}",
                    retryable=True,
                ) from exc
        return self._session

    def publish(self, request: PublishRequest) -> PublishResult:
        video = request.video_path.expanduser().resolve()
        if not video.is_file():
            raise PublisherError(
                "FACEBOOK_VIDEO_MISSING", f"Không tìm thấy video đã sửa: {video}"
            )
        expected_hash = str(request.options.get("video_sha256") or "").strip().lower()
        if expected_hash and _sha256_file(video) != expected_hash:
            raise PublisherError(
                "FACEBOOK_VIDEO_CHANGED",
                "Video đã sửa đổi sau khi được khóa. Ứng dụng dừng để tránh đăng sai file.",
            )

        try:
            target = _business_suite_url(self.page_id)
        except ValueError as exc:
            raise PublisherError("FACEBOOK_PAGE_ID_INVALID", str(exc)) from exc

        session = self._browser()
        try:
            session.goto(target, timeout_ms=self.navigation_timeout_ms)
        except Exception as exc:
            raise PublisherError(
                "FACEBOOK_NAVIGATION_FAILED",
                f"Không mở được trang tải Reel của Fanpage: {exc}",
                retryable=True,
            ) from exc

        try:
            body = session.body_text()
        except Exception:
            body = ""
        if _contains_any(body, LOGIN_MARKERS) or not _is_trusted_composer_url(
            session.url, self.page_id
        ):
            raise PublisherError(
                "FACEBOOK_AUTHENTICATION_REQUIRED",
                "Facebook chưa sẵn sàng trong Chrome dùng chung. Hãy đăng nhập/chọn "
                "đúng Fanpage trong cửa sổ Chrome rồi bấm Đăng FB lại.",
                retryable=True,
            )

        upload_input = session.first_present(
            UPLOAD_INPUT_SELECTORS, timeout_ms=self.control_timeout_ms
        )
        if upload_input is None:
            raise PublisherError(
                "FACEBOOK_UPLOAD_INPUT_NOT_FOUND",
                "Đã mở Meta Business Suite nhưng chưa thấy ô chọn video. Hãy kiểm "
                "tra quyền Fanpage trong Chrome; ứng dụng chưa tải file nào.",
                retryable=True,
            )
        try:
            session.set_input_files(upload_input, video)
            session.wait(self.upload_settle_ms)
        except Exception as exc:
            raise PublisherError(
                "FACEBOOK_UPLOAD_NOT_STARTED",
                f"Không đưa được video đã sửa vào Facebook: {exc}",
                retryable=True,
            ) from exc

        caption_filled = False
        caption_input = session.first_visible(
            CAPTION_INPUT_SELECTORS, timeout_ms=self.control_timeout_ms
        )
        if caption_input is not None and request.caption.strip():
            try:
                session.fill(caption_input, request.caption)
                caption_filled = True
            except Exception:
                caption_filled = False

        return PublishResult(
            state=STATE_AWAITING_CONFIRMATION,
            metadata={
                "mode": "shared_chrome",
                "video_uploaded": True,
                "caption_filled": caption_filled,
                "publish_action_performed": False,
                "page_id": self.page_id,
            },
            message=(
                "Đã đưa video đã sửa vào Fanpage trong Chrome dùng chung"
                + (" và điền caption." if caption_filled else ".")
                + " Hãy kiểm tra rồi bấm Đăng/Lên lịch trong Facebook."
            ),
        )

    def close(self) -> None:
        session = self._session
        self._session = None
        if session is not None:
            session.close()


__all__ = ["FacebookBrowserPublisher", "STATE_AWAITING_CONFIRMATION"]
