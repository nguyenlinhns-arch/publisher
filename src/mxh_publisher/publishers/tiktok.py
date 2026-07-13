"""Human-controlled TikTok Studio publishing assistance.

This adapter deliberately stops before the irreversible action.  It opens a
headed, persistent browser profile, selects the video, fills the caption when
possible, captures evidence, and leaves TikTok Studio open for the operator to
review.  There is intentionally no call to a browser ``click`` method in this
module, so neither the Post nor Schedule action can be triggered by it.

The browser-facing surface is kept behind :class:`BrowserSession`.  Besides
making unit tests deterministic, that keeps TikTok selectors in one small,
easy-to-update section when Studio changes its markup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
from time import monotonic
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from .base import PublishRequest, PublishResult, PublisherError


DEFAULT_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
SCREENSHOT_RETENTION_DAYS = 7

STATE_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATE_AUTHENTICATION_REQUIRED = "authentication_required"
STATE_VERIFICATION_REQUIRED = "verification_required"
STATE_MANUAL_ACTION_REQUIRED = "manual_action_required"


# Keep all DOM knowledge here.  Prefer semantic attributes and roles, with a
# small generic fallback last.  No selector below is ever used for clicking.
UPLOAD_INPUT_SELECTORS: tuple[str, ...] = (
    'input[type="file"][accept*="video"]',
    '[data-e2e="upload-card"] input[type="file"]',
    '[data-testid="upload-input"]',
    'input[type="file"]',
)

CAPTION_INPUT_SELECTORS: tuple[str, ...] = (
    '[data-e2e="caption"] [contenteditable="true"]',
    '[data-testid="caption"] [contenteditable="true"]',
    '[contenteditable="true"][role="textbox"]',
    'textarea[name="caption"]',
    '[contenteditable="true"]',
    "textarea",
)

# Merely observing one of these controls is useful evidence that Studio has
# reached its review surface.  The adapter never invokes it.
PREVIEW_READY_SELECTORS: tuple[str, ...] = (
    '[data-e2e="post_video_button"]',
    '[data-testid="post-button"]',
    'button:has-text("Post")',
    'button:has-text("Đăng")',
    'button:has-text("Schedule")',
    'button:has-text("Lên lịch")',
)


CAPTCHA_TEXT_MARKERS: tuple[str, ...] = (
    "captcha",
    "verify to continue",
    "security verification",
    "drag the slider",
    "complete the puzzle",
    "xác minh để tiếp tục",
    "xác minh bảo mật",
    "kéo thanh trượt",
    "hoàn thành câu đố",
)

TWO_FACTOR_TEXT_MARKERS: tuple[str, ...] = (
    "two-step verification",
    "2-step verification",
    "two-factor authentication",
    "enter verification code",
    "enter the 6-digit code",
    "verification code has been sent",
    "xác thực hai bước",
    "xác minh 2 bước",
    "nhập mã xác minh",
    "nhập mã gồm 6 chữ số",
    "mã xác minh đã được gửi",
)

LOGIN_TEXT_MARKERS: tuple[str, ...] = (
    "log in to tiktok",
    "login to tiktok",
    "đăng nhập vào tiktok",
)

LOGIN_URL_MARKERS: tuple[str, ...] = (
    "/login",
    "/signin",
)


class BrowserSession(Protocol):
    """The minimal, non-mutating-after-preview browser surface we need."""

    @property
    def url(self) -> str:
        """Return the active page URL."""

    def goto(self, url: str, *, timeout_ms: int) -> None:
        """Navigate to TikTok Studio."""

    def body_text(self) -> str:
        """Return visible page text for login/challenge detection."""

    def first_present(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        """Return the first selector in the DOM, even when the input is hidden."""

    def first_visible(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        """Return the first currently visible selector, waiting if requested."""

    def set_input_files(self, selector: str, path: Path) -> None:
        """Assign a local file to an upload input without clicking."""

    def fill(self, selector: str, value: str) -> None:
        """Fill a textarea or contenteditable element without submitting."""

    def wait(self, milliseconds: int) -> None:
        """Allow client-side upload state to progress."""

    def screenshot(self, path: Path) -> None:
        """Capture the current page."""

    def close(self) -> None:
        """Close the persistent browser when the application exits."""


BrowserSessionFactory = Callable[[Path, str, bool], BrowserSession]


@dataclass(frozen=True, slots=True)
class _Challenge:
    kind: str
    evidence: str


@dataclass(frozen=True, slots=True)
class TikTokConnectionResult:
    connected: bool
    message: str


def _default_app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "MXHPublisher"


def _safe_url(value: str) -> str:
    """Drop credentials, query and fragment before placing a URL in logs."""

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return ""
    if not parts.scheme:
        return value.split("?", 1)[0].split("#", 1)[0]
    hostname = parts.hostname or ""
    if not hostname:
        return ""
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _validate_configured_upload_url(value: str) -> str:
    """Accept only TikTok Studio's exact, non-parameterised upload URL."""

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("URL tải lên TikTok không hợp lệ.") from exc
    if (
        parts.scheme != "https"
        or parts.hostname != "www.tiktok.com"
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or parts.path != "/tiktokstudio/upload"
        or bool(parts.query)
        or bool(parts.fragment)
    ):
        raise ValueError(
            "URL tải lên TikTok phải chính xác là "
            "https://www.tiktok.com/tiktokstudio/upload."
        )
    return DEFAULT_UPLOAD_URL


def _is_trusted_studio_url(value: str) -> bool:
    """Return whether a post-navigation URL remains inside TikTok Studio."""

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname == "www.tiktok.com"
        and parts.username is None
        and parts.password is None
        and port is None
        and parts.path.startswith("/tiktokstudio/")
    )


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_any(value: str, markers: Sequence[str]) -> str | None:
    folded = re.sub(r"\s+", " ", value).casefold()
    return next((marker for marker in markers if marker.casefold() in folded), None)


def _detect_challenge(session: BrowserSession) -> _Challenge | None:
    """Detect CAPTCHA, 2FA, then login without attempting to bypass any."""

    try:
        text = session.body_text()
    except Exception:
        text = ""
    safe_url = _safe_url(session.url).casefold()

    if marker := _contains_any(text, CAPTCHA_TEXT_MARKERS):
        return _Challenge("captcha", marker)
    if marker := _contains_any(text, TWO_FACTOR_TEXT_MARKERS):
        return _Challenge("two_factor", marker)
    if any(marker in safe_url for marker in LOGIN_URL_MARKERS):
        return _Challenge("login", "login_url")
    if marker := _contains_any(text, LOGIN_TEXT_MARKERS):
        return _Challenge("login", marker)
    return None


class _PlaywrightBrowserSession:
    """Thin synchronous Playwright wrapper used only by the default factory."""

    def __init__(self, profile_dir: Path, browser_channel: str, headless: bool) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(
                "Chưa cài Playwright. Hãy cài playwright và Microsoft Edge."
            ) from exc

        requested = browser_channel.strip().lower()
        if not requested or requested == "chromium":
            raise RuntimeError(
                "Phải cấu hình một kênh trình duyệt đã cài đặt, ví dụ msedge; "
                "không dùng Chromium dự phòng."
            )

        self._manager: Any | None = sync_playwright().start()
        self._context = None
        self._closed = False
        profile_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._context = self._manager.chromium.launch_persistent_context(
                str(profile_dir),
                channel=requested,
                headless=headless,
                no_viewport=True,
                args=["--start-maximized"],
            )
        except Exception as exc:  # pragma: no cover - browser installation-specific
            manager = self._manager
            self._manager = None
            manager.stop()
            raise RuntimeError(
                f"Không mở được kênh trình duyệt bắt buộc {requested}: {exc}"
            ) from exc

        self._page = (
            self._context.pages[0] if self._context.pages else self._context.new_page()
        )

    @property
    def url(self) -> str:
        return self._page.url

    def goto(self, url: str, *, timeout_ms: int) -> None:
        self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    def body_text(self) -> str:
        return self._page.locator("body").inner_text(timeout=3_000)

    def first_present(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        deadline = monotonic() + max(timeout_ms, 0) / 1_000
        while True:
            for selector in selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        return selector
                except Exception:
                    continue
            if monotonic() >= deadline:
                return None
            self._page.wait_for_timeout(250)

    def first_visible(self, selectors: Sequence[str], *, timeout_ms: int) -> str | None:
        deadline = monotonic() + max(timeout_ms, 0) / 1_000
        while True:
            for selector in selectors:
                try:
                    if self._page.locator(selector).first.is_visible():
                        return selector
                except Exception:
                    # A selector unsupported by an older Playwright build should
                    # not prevent later fallbacks from being considered.
                    continue
            if monotonic() >= deadline:
                return None
            self._page.wait_for_timeout(250)

    def set_input_files(self, selector: str, path: Path) -> None:
        self._page.locator(selector).first.set_input_files(str(path))

    def fill(self, selector: str, value: str) -> None:
        self._page.locator(selector).first.fill(value)

    def wait(self, milliseconds: int) -> None:
        self._page.wait_for_timeout(milliseconds)

    def screenshot(self, path: Path) -> None:
        self._page.screenshot(path=str(path), full_page=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._context is not None:
                self._context.close()
                self._context = None
        finally:
            manager = self._manager
            self._manager = None
            if manager is not None:
                manager.stop()


def start_playwright_session(
    profile_dir: Path, browser_channel: str, headless: bool
) -> BrowserSession:
    return _PlaywrightBrowserSession(profile_dir, browser_channel, headless)


class TikTokPublisher:
    """Prepare a TikTok Studio post and require an operator confirmation."""

    platform = "tiktok"

    def __init__(
        self,
        *,
        browser_profile_dir: Path | None = None,
        screenshots_dir: Path | None = None,
        upload_url: str = DEFAULT_UPLOAD_URL,
        browser_channel: str = "msedge",
        session_factory: BrowserSessionFactory | None = None,
        navigation_timeout_ms: int = 45_000,
        control_timeout_ms: int = 20_000,
        preview_timeout_ms: int = 30_000,
        upload_settle_ms: int = 1_500,
    ) -> None:
        app_data = _default_app_data_dir()
        self.browser_profile_dir = (
            (browser_profile_dir or app_data / "browser_profile" / "tiktok")
            .expanduser()
            .resolve()
        )
        self.screenshots_dir = (
            (screenshots_dir or app_data / "screenshots" / "tiktok")
            .expanduser()
            .resolve()
        )
        self.upload_url = _validate_configured_upload_url(upload_url)
        self.browser_channel = browser_channel
        self._session_factory = session_factory or start_playwright_session
        self.navigation_timeout_ms = navigation_timeout_ms
        self.control_timeout_ms = control_timeout_ms
        self.preview_timeout_ms = preview_timeout_ms
        self.upload_settle_ms = upload_settle_ms
        self._session: BrowserSession | None = None

        # A browser profile contains authenticated session material.  Keeping it
        # outside the repository prevents accidental commits and project copies.
        project_root = Path(__file__).resolve().parents[3]
        if (
            self.browser_profile_dir == project_root
            or project_root in self.browser_profile_dir.parents
        ):
            raise ValueError("Hồ sơ trình duyệt TikTok phải nằm ngoài thư mục dự án.")

    def _browser(self) -> BrowserSession:
        if self._session is not None:
            return self._session
        try:
            # Headed is a safety property here: the operator must be able to see
            # and review everything TikTok displays.
            self._session = self._session_factory(
                self.browser_profile_dir, self.browser_channel, False
            )
        except Exception as exc:
            raise PublisherError(
                "TIKTOK_BROWSER_START_FAILED",
                f"Không mở được kênh trình duyệt bắt buộc cho TikTok: {exc}",
                retryable=True,
                unknown_outcome=False,
            ) from exc
        return self._session

    def check_connection(self) -> TikTokConnectionResult:
        """Open Studio in the dedicated profile and inspect login state only."""
        session = self._browser()
        try:
            session.goto(self.upload_url, timeout_ms=self.navigation_timeout_ms)
        except Exception as exc:
            return TikTokConnectionResult(False, f"Không mở được TikTok Studio: {exc}")
        challenge = _detect_challenge(session)
        if challenge is not None:
            if challenge.kind == "login":
                return TikTokConnectionResult(
                    False,
                    "TikTok chưa đăng nhập. Hãy đăng nhập trong cửa sổ Edge vừa mở, "
                    "sau đó bấm Kiểm tra lại.",
                )
            return TikTokConnectionResult(
                False,
                "TikTok yêu cầu CAPTCHA hoặc mã xác minh. Hãy tự hoàn tất trong "
                "cửa sổ Edge rồi bấm Kiểm tra lại.",
            )
        if not _is_trusted_studio_url(session.url):
            return TikTokConnectionResult(
                False, "TikTok đã chuyển khỏi Studio; chưa thể xác nhận kết nối."
            )
        upload = session.first_present(UPLOAD_INPUT_SELECTORS, timeout_ms=5_000)
        if upload is None:
            return TikTokConnectionResult(
                False,
                "Đã mở TikTok Studio nhưng chưa xác nhận được phiên đăng nhập. "
                "Hãy kiểm tra cửa sổ Edge.",
            )
        return TikTokConnectionResult(
            True, "TikTok Studio đã đăng nhập và sẵn sàng chuẩn bị video."
        )

    def _capture(
        self, session: BrowserSession, request: PublishRequest, label: str
    ) -> tuple[str | None, str | None]:
        # Authentication and verification screens can contain QR codes, account
        # details or one-time challenges.  Guard centrally so every capture path
        # (including an upload exception) observes the no-screenshot rule.
        if _detect_challenge(session) is not None:
            return None, "screenshot_skipped_sensitive_authentication_challenge"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._purge_old_screenshots()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        safe_label = re.sub(r"[^a-z0-9_-]+", "-", label.casefold()).strip("-")
        path = self.screenshots_dir / (
            f"tiktok_{request.post_id}_{timestamp}_{safe_label or 'state'}.png"
        )
        try:
            session.screenshot(path)
        except Exception as exc:
            return None, str(exc)
        return str(path), None

    def _purge_old_screenshots(self) -> None:
        cutoff = datetime.now(UTC).timestamp() - (
            SCREENSHOT_RETENTION_DAYS * 24 * 60 * 60
        )
        for path in self.screenshots_dir.glob("tiktok_*.png"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                # Screenshot retention must not hide the primary publishing state.
                continue

    def _challenge_result(
        self,
        session: BrowserSession,
        request: PublishRequest,
        challenge: _Challenge,
        *,
        phase: str,
    ) -> PublishResult:
        if challenge.kind == "login":
            state = STATE_AUTHENTICATION_REQUIRED
            message = (
                "TikTok yêu cầu đăng nhập. Hãy đăng nhập trực tiếp trong cửa sổ "
                "Edge rồi chạy lại; ứng dụng không lưu mật khẩu."
            )
        else:
            state = STATE_VERIFICATION_REQUIRED
            message = (
                "TikTok đang yêu cầu CAPTCHA hoặc mã xác minh. Ứng dụng đã dừng; "
                "hãy tự hoàn tất kiểm tra trong cửa sổ trình duyệt rồi chạy lại."
            )
        return PublishResult(
            state=state,
            metadata={
                "mode": "assisted",
                "challenge": challenge.kind,
                "challenge_evidence": challenge.evidence,
                "phase": phase,
                "current_url": _safe_url(session.url),
                "screenshot_path": None,
                "screenshot_error": None,
                "screenshot_skipped_reason": "sensitive_authentication_challenge",
                "publish_action_performed": False,
                "schedule_action_performed": False,
            },
            message=message,
        )

    def _manual_result(
        self,
        session: BrowserSession,
        request: PublishRequest,
        *,
        reason: str,
        message: str,
        extra_metadata: dict[str, object] | None = None,
    ) -> PublishResult:
        screenshot, screenshot_error = self._capture(session, request, reason)
        metadata: dict[str, object] = {
            "mode": "assisted",
            "reason": reason,
            "current_url": _safe_url(session.url),
            "screenshot_path": screenshot,
            "screenshot_error": screenshot_error,
            "publish_action_performed": False,
            "schedule_action_performed": False,
        }
        metadata.update(extra_metadata or {})
        return PublishResult(
            state=STATE_MANUAL_ACTION_REQUIRED,
            metadata=metadata,
            message=message,
        )

    def publish(self, request: PublishRequest) -> PublishResult:
        """Prepare TikTok Studio and stop before Post/Schedule confirmation.

        The method name follows the common publisher contract.  For TikTok V1
        its successful terminal state is ``awaiting_confirmation``, never
        ``published``.
        """

        video_path = request.video_path.expanduser().resolve()
        if not video_path.is_file():
            raise PublisherError(
                "TIKTOK_VIDEO_NOT_FOUND",
                f"Không tìm thấy video TikTok: {video_path}",
                retryable=False,
                unknown_outcome=False,
            )

        session = self._browser()
        try:
            session.goto(self.upload_url, timeout_ms=self.navigation_timeout_ms)
        except Exception as exc:
            raise PublisherError(
                "TIKTOK_NAVIGATION_FAILED",
                f"Không mở được TikTok Studio: {exc}",
                retryable=True,
                unknown_outcome=False,
            ) from exc

        if challenge := _detect_challenge(session):
            return self._challenge_result(
                session, request, challenge, phase="before_upload"
            )

        if not _is_trusted_studio_url(session.url):
            raise PublisherError(
                "TIKTOK_UNTRUSTED_PAGE",
                "TikTok Studio đã chuyển sang một trang không được tin cậy; "
                "ứng dụng đã chặn việc chọn video.",
                retryable=False,
                unknown_outcome=False,
                metadata={
                    "current_url": _safe_url(session.url),
                    "publish_action_performed": False,
                    "schedule_action_performed": False,
                },
            )

        # File inputs are commonly hidden behind TikTok's styled upload card.
        # Playwright can safely assign a file to a hidden input, so presence—not
        # visual visibility—is the correct test here.
        upload_selector = session.first_present(
            UPLOAD_INPUT_SELECTORS, timeout_ms=self.control_timeout_ms
        )
        if upload_selector is None:
            return self._manual_result(
                session,
                request,
                reason="upload_control_not_found",
                message=(
                    "Không tìm thấy vùng chọn video của TikTok Studio. Ứng dụng đã "
                    "dừng để tránh thao tác nhầm; có thể giao diện TikTok đã thay đổi."
                ),
            )

        expected_sha256_value = request.options.get("video_sha256")
        if expected_sha256_value is not None:
            if not isinstance(expected_sha256_value, str) or re.fullmatch(
                r"[0-9a-fA-F]{64}", expected_sha256_value.strip()
            ) is None:
                raise PublisherError(
                    "TIKTOK_INVALID_VIDEO_SHA256",
                    "SHA-256 dùng để kiểm tra video TikTok không hợp lệ.",
                    retryable=False,
                    unknown_outcome=False,
                )
            expected_sha256 = expected_sha256_value.strip().lower()
            try:
                actual_sha256 = _sha256_file(video_path)
            except OSError as exc:
                raise PublisherError(
                    "TIKTOK_VIDEO_UNREADABLE",
                    f"Không đọc được video ngay trước khi tải lên TikTok: {exc}",
                    retryable=False,
                    unknown_outcome=False,
                ) from exc
            if actual_sha256 != expected_sha256:
                raise PublisherError(
                    "TIKTOK_VIDEO_CHANGED",
                    "Video đã thay đổi sau khi được duyệt; ứng dụng đã chặn tải lên.",
                    retryable=False,
                    unknown_outcome=False,
                    metadata={
                        "expected_video_sha256": expected_sha256,
                        "actual_video_sha256": actual_sha256,
                        "publish_action_performed": False,
                        "schedule_action_performed": False,
                    },
                )

        # Re-check immediately before exposing the local file.  The page can
        # navigate while controls are being discovered or the digest is read.
        if not _is_trusted_studio_url(session.url):
            raise PublisherError(
                "TIKTOK_UNTRUSTED_PAGE",
                "TikTok Studio đã chuyển sang một trang không được tin cậy; "
                "ứng dụng đã chặn việc chọn video.",
                retryable=False,
                unknown_outcome=False,
                metadata={
                    "current_url": _safe_url(session.url),
                    "publish_action_performed": False,
                    "schedule_action_performed": False,
                },
            )

        try:
            session.set_input_files(upload_selector, video_path)
            session.wait(self.upload_settle_ms)
        except Exception as exc:
            screenshot, screenshot_error = self._capture(
                session, request, "upload-failed"
            )
            raise PublisherError(
                "TIKTOK_UPLOAD_FAILED",
                f"Không đưa được video vào TikTok Studio: {exc}",
                retryable=True,
                unknown_outcome=False,
                metadata={
                    "screenshot_path": screenshot,
                    "screenshot_error": screenshot_error,
                    "publish_action_performed": False,
                },
            ) from exc

        if challenge := _detect_challenge(session):
            return self._challenge_result(
                session, request, challenge, phase="after_upload"
            )

        caption_selector = session.first_visible(
            CAPTION_INPUT_SELECTORS, timeout_ms=self.control_timeout_ms
        )
        caption_filled = False
        caption_fill_error: str | None = None
        if caption_selector is not None:
            try:
                session.fill(caption_selector, request.caption)
                caption_filled = True
            except Exception as exc:
                # Caption entry is best-effort.  The operator can still enter it
                # safely on the review screen; no irreversible action occurred.
                caption_fill_error = str(exc)

        if challenge := _detect_challenge(session):
            return self._challenge_result(
                session, request, challenge, phase="after_caption"
            )

        preview_selector = session.first_visible(
            PREVIEW_READY_SELECTORS, timeout_ms=self.preview_timeout_ms
        )
        scheduled_at = (
            request.scheduled_at_utc.isoformat()
            if request.scheduled_at_utc is not None
            else None
        )

        # A challenge can appear while a large video is being processed.  Check
        # again after the preview wait before deciding that the page is ready.
        if challenge := _detect_challenge(session):
            return self._challenge_result(
                session, request, challenge, phase="waiting_for_preview"
            )

        if preview_selector is None:
            return self._manual_result(
                session,
                request,
                reason="preview_not_ready",
                message=(
                    "Đã đưa video vào TikTok Studio nhưng chưa thấy bằng chứng màn "
                    "hình preview/upload-ready. Ứng dụng đã dừng và không bấm Đăng "
                    "hoặc Lên lịch; hãy kiểm tra trực tiếp trong trình duyệt."
                ),
                extra_metadata={
                    "video_uploaded": True,
                    "caption_filled": caption_filled,
                    "caption_control_found": caption_selector is not None,
                    "caption_fill_error": caption_fill_error,
                    "preview_detected": False,
                    "requested_scheduled_at_utc": scheduled_at,
                    "confirmation_required": True,
                },
            )

        screenshot, screenshot_error = self._capture(session, request, "preview")
        return PublishResult(
            state=STATE_AWAITING_CONFIRMATION,
            remote_id=None,
            permalink_url=None,
            metadata={
                "mode": "assisted",
                "current_url": _safe_url(session.url),
                "video_uploaded": True,
                "caption_filled": caption_filled,
                "caption_control_found": caption_selector is not None,
                "caption_fill_error": caption_fill_error,
                "preview_detected": preview_selector is not None,
                "screenshot_path": screenshot,
                "screenshot_error": screenshot_error,
                "requested_scheduled_at_utc": scheduled_at,
                "publish_action_performed": False,
                "schedule_action_performed": False,
                "confirmation_required": True,
            },
            message=(
                "Video đã được đưa vào TikTok Studio"
                + (
                    " và caption đã được điền. "
                    if caption_filled
                    else ". Caption cần được kiểm tra/điền thủ công. "
                )
                + "Ứng dụng không bấm Đăng hoặc Lên lịch; hãy kiểm tra preview, "
                "tự chọn lịch nếu cần và tự xác nhận trong trình duyệt."
            ),
        )

    def close(self) -> None:
        """Close the browser explicitly, normally when the desktop app exits."""

        if self._session is None:
            return
        try:
            self._session.close()
        finally:
            self._session = None


# More explicit alias for callers that want the safety mode visible in code.
TikTokAssistedPublisher = TikTokPublisher


__all__ = [
    "BrowserSession",
    "CAPTION_INPUT_SELECTORS",
    "PREVIEW_READY_SELECTORS",
    "STATE_AUTHENTICATION_REQUIRED",
    "STATE_AWAITING_CONFIRMATION",
    "STATE_MANUAL_ACTION_REQUIRED",
    "STATE_VERIFICATION_REQUIRED",
    "TikTokAssistedPublisher",
    "TikTokPublisher",
    "UPLOAD_INPUT_SELECTORS",
]
