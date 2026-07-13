from __future__ import annotations

import sqlite3
from pathlib import Path

from mxh_publisher.services.browser_connections import ChromeLoginManager


class RecordingLauncher:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, str]] = []

    def __call__(self, executable: Path, profile: Path, url: str) -> None:
        self.calls.append((executable, profile, url))


def _write_cookie(profile: Path, host: str, name: str) -> None:
    database = profile / "Default" / "Network" / "Cookies"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB)"
        )
        connection.execute(
            "INSERT INTO cookies VALUES (?, ?, '', ?)", (host, name, b"encrypted")
        )


def _manager(tmp_path: Path, launcher: RecordingLauncher) -> ChromeLoginManager:
    return ChromeLoginManager(
        tmp_path / "chrome-profile",
        launcher=launcher,
        chrome_executable=tmp_path / "chrome.exe",
    )


def test_facebook_saved_cookie_is_connected_and_opens_normal_chrome(
    tmp_path: Path,
) -> None:
    launcher = RecordingLauncher()
    manager = _manager(tmp_path, launcher)
    _write_cookie(manager.profile_dir, ".facebook.com", "c_user")

    result = manager.open_facebook()

    assert result.connected
    assert "Đã kết nối" in result.message
    assert launcher.calls[0][2] == "https://www.facebook.com/"


def test_tiktok_without_cookie_opens_login_and_requests_check_again(
    tmp_path: Path,
) -> None:
    launcher = RecordingLauncher()
    manager = _manager(tmp_path, launcher)

    result = manager.open_tiktok()

    assert not result.connected
    assert "Chrome thường" in result.message
    assert "tiktok.com/login" in launcher.calls[0][2]


def test_tiktok_session_cookie_is_connected(tmp_path: Path) -> None:
    launcher = RecordingLauncher()
    manager = _manager(tmp_path, launcher)
    _write_cookie(manager.profile_dir, ".tiktok.com", "sessionid")

    result = manager.open_tiktok()

    assert result.connected
    assert "đóng toàn bộ" in result.message
