from pathlib import Path
from typing import Sequence

from mxh_publisher.services.browser_connections import FacebookBrowserConnection


class FakeBrowser:
    def __init__(self, *, url: str, body: str) -> None:
        self._url = url
        self.body = body
        self.operations: list[str] = []

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, *, timeout_ms: int) -> None:
        self.operations.append("goto")

    def body_text(self) -> str:
        self.operations.append("body_text")
        return self.body

    def first_present(self, selectors: Sequence[str], *, timeout_ms: int):
        return None

    def first_visible(self, selectors: Sequence[str], *, timeout_ms: int):
        return None

    def set_input_files(self, selector: str, path: Path) -> None:
        raise AssertionError("Facebook connection must not select a file")

    def fill(self, selector: str, value: str) -> None:
        raise AssertionError("Facebook connection must not fill credentials")

    def wait(self, milliseconds: int) -> None:
        pass

    def screenshot(self, path: Path) -> None:
        raise AssertionError("Facebook connection must not capture login screens")

    def close(self) -> None:
        self.operations.append("close")


def _connection(tmp_path: Path, browser: FakeBrowser) -> FacebookBrowserConnection:
    return FacebookBrowserConnection(
        tmp_path / "facebook-profile",
        session_factory=lambda *_args: browser,
    )


def test_facebook_logged_in_session_is_connected(tmp_path: Path) -> None:
    browser = FakeBrowser(
        url="https://www.facebook.com/", body="Home Friends Notifications"
    )

    result = _connection(tmp_path, browser).open_and_check()

    assert result.connected
    assert "Đã kết nối" in result.message
    assert browser.operations == ["goto", "body_text"]


def test_facebook_login_page_is_not_connected(tmp_path: Path) -> None:
    browser = FakeBrowser(
        url="https://www.facebook.com/login/", body="Log into Facebook"
    )

    result = _connection(tmp_path, browser).open_and_check()

    assert not result.connected
    assert "đăng nhập" in result.message.casefold()
