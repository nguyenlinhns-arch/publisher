from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..publishers.tiktok import BrowserSession, BrowserSessionFactory, start_playwright_session


FACEBOOK_HOME_URL = "https://www.facebook.com/"
FACEBOOK_LOGIN_MARKERS = (
    "log into facebook",
    "log in to facebook",
    "đăng nhập facebook",
    "email or phone",
    "email hoặc số điện thoại",
)


@dataclass(frozen=True, slots=True)
class BrowserConnectionResult:
    connected: bool
    message: str


class FacebookBrowserConnection:
    """Own a visible, persistent Edge profile used only for Facebook login."""

    def __init__(
        self,
        profile_dir: Path,
        *,
        browser_channel: str = "msedge",
        session_factory: BrowserSessionFactory | None = None,
    ) -> None:
        self.profile_dir = profile_dir.expanduser().resolve()
        self.browser_channel = browser_channel
        self._session_factory = session_factory or start_playwright_session
        self._session: BrowserSession | None = None

    def _browser(self) -> BrowserSession:
        if self._session is None:
            self._session = self._session_factory(
                self.profile_dir, self.browser_channel, False
            )
        return self._session

    def open_and_check(self) -> BrowserConnectionResult:
        try:
            session = self._browser()
            session.goto(FACEBOOK_HOME_URL, timeout_ms=45_000)
            current_url = session.url
            body = session.body_text().casefold()
        except Exception as exc:
            return BrowserConnectionResult(
                False, f"Không mở được Facebook bằng Edge: {exc}"
            )
        parts = urlsplit(current_url)
        login_page = "/login" in parts.path.casefold()
        login_text = any(marker in body for marker in FACEBOOK_LOGIN_MARKERS)
        trusted_host = parts.hostname in {"facebook.com", "www.facebook.com"}
        if trusted_host and not login_page and not login_text:
            return BrowserConnectionResult(
                True,
                "Đã kết nối Facebook. Phiên đăng nhập đã được lưu trong hồ sơ "
                "Edge riêng của ứng dụng.",
            )
        return BrowserConnectionResult(
            False,
            "Facebook đã được mở. Hãy đăng nhập trực tiếp trong cửa sổ Edge, "
            "sau đó bấm Kiểm tra lại.",
        )

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
