from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


FACEBOOK_HOME_URL = "https://www.facebook.com/"
TIKTOK_LOGIN_URL = (
    "https://www.tiktok.com/login?redirect_url="
    "https%3A%2F%2Fwww.tiktok.com%2Ftiktokstudio%2Fupload"
)
DEVTOOLS_ACTIVE_PORT_FILE = "DevToolsActivePort"


@dataclass(frozen=True, slots=True)
class BrowserConnectionResult:
    connected: bool
    message: str


Launcher = Callable[[Path, Path, str], None]


def find_google_chrome() -> Path:
    """Find the normal Google Chrome executable without invoking Playwright."""

    candidates: list[Path] = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for name in ("chrome", "google-chrome", "google-chrome-stable"):
        executable = shutil.which(name)
        if executable:
            candidates.append(Path(executable))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Không tìm thấy Google Chrome. Hãy cài Google Chrome rồi thử lại.")


def launch_normal_chrome(executable: Path, profile_dir: Path, url: str) -> None:
    """Open detached Chrome with the app profile and a local automation endpoint.

    Chrome remains an ordinary, user-visible browser.  The local endpoint lets
    the publisher attach to this *same process* later instead of starting a
    second browser that loses login state or locks the profile.
    """

    profile_dir.mkdir(parents=True, exist_ok=True)
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    subprocess.Popen(
        [
            str(executable),
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            "--start-maximized",
            url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags,
    )


def read_devtools_port(profile_dir: Path) -> int | None:
    """Return the live Chrome debugging port recorded in the app profile."""

    marker = profile_dir / DEVTOOLS_ACTIVE_PORT_FILE
    try:
        first_line = marker.read_text(encoding="utf-8").splitlines()[0].strip()
        port = int(first_line)
    except (OSError, ValueError, IndexError):
        return None
    return port if 1 <= port <= 65535 else None


def wait_for_devtools_port(profile_dir: Path, timeout_seconds: float = 10.0) -> int | None:
    """Wait briefly for Chrome to expose its local endpoint after launch."""

    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while True:
        if port := read_devtools_port(profile_dir):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    return port
            except OSError:
                pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.2)


class ChromeLoginManager:
    """Open login pages in normal Chrome and detect saved login cookies.

    Login is intentionally outside Playwright. This avoids TikTok pausing its
    login popup because a debugger/automation connection is attached.
    """

    def __init__(
        self,
        profile_dir: Path,
        *,
        launcher: Launcher | None = None,
        chrome_executable: Path | None = None,
    ) -> None:
        self.profile_dir = profile_dir.expanduser().resolve()
        self._launcher = launcher or launch_normal_chrome
        self._chrome_executable = chrome_executable

    def _cookie_databases(self) -> tuple[Path, ...]:
        return (
            self.profile_dir / "Default" / "Network" / "Cookies",
            self.profile_dir / "Default" / "Cookies",
            self.profile_dir / "Network" / "Cookies",
        )

    @staticmethod
    def _database_has_cookie(
        database: Path, *, domain: str, cookie_names: tuple[str, ...]
    ) -> bool:
        if not database.is_file():
            return False
        placeholders = ",".join("?" for _ in cookie_names)
        query = (
            "SELECT 1 FROM cookies WHERE host_key LIKE ? "
            f"AND name IN ({placeholders}) "
            "AND (length(value) > 0 OR length(encrypted_value) > 0) LIMIT 1"
        )
        parameters = (f"%{domain}", *cookie_names)
        try:
            uri = database.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=1) as connection:
                return connection.execute(query, parameters).fetchone() is not None
        except (OSError, sqlite3.Error):
            pass
        try:
            with tempfile.TemporaryDirectory(prefix="mxh-cookies-") as directory:
                copied = Path(directory) / "Cookies"
                shutil.copy2(database, copied)
                for suffix in ("-wal", "-shm"):
                    companion = Path(str(database) + suffix)
                    if companion.is_file():
                        shutil.copy2(companion, Path(str(copied) + suffix))
                with sqlite3.connect(copied) as connection:
                    row = connection.execute(query, parameters).fetchone()
                return row is not None
        except (OSError, sqlite3.Error):
            return False

    def _has_cookie(self, *, domain: str, cookie_names: tuple[str, ...]) -> bool:
        return any(
            self._database_has_cookie(
                database, domain=domain, cookie_names=cookie_names
            )
            for database in self._cookie_databases()
        )

    def _open(self, url: str) -> None:
        executable = self._chrome_executable or find_google_chrome()
        self._launcher(executable, self.profile_dir, url)

    def open_facebook(self) -> BrowserConnectionResult:
        connected = self._has_cookie(domain="facebook.com", cookie_names=("c_user",))
        self._open(FACEBOOK_HOME_URL)
        if connected:
            return BrowserConnectionResult(
                True,
                "Đã nhận phiên Facebook trong Chrome dùng chung. Hãy giữ Chrome mở; "
                "nút Đăng FB sẽ đưa video đã sửa vào chính cửa sổ này.",
            )
        return BrowserConnectionResult(
            False,
            "Facebook đã mở trong Chrome dùng chung. Hãy đăng nhập và giữ Chrome mở; "
            "sau đó có thể bấm Đăng FB trực tiếp.",
        )

    def open_tiktok(self) -> BrowserConnectionResult:
        connected = self._has_cookie(
            domain="tiktok.com",
            cookie_names=(
                "sessionid",
                "sessionid_ss",
                "sid_tt",
                "sid_guard",
                "uid_tt",
                "uid_tt_ss",
                "passport_auth_status",
                "passport_auth_status_ss",
            ),
        )
        if connected:
            self._open("https://www.tiktok.com/tiktokstudio/upload")
            return BrowserConnectionResult(
                True,
                "Đã nhận phiên TikTok trong Chrome dùng chung. Hãy giữ Chrome mở; "
                "nút Đăng TikTok sẽ dùng chính cửa sổ này.",
            )
        self._open(TIKTOK_LOGIN_URL)
        return BrowserConnectionResult(
            False,
            "TikTok đã mở trong Chrome dùng chung. Hãy đăng nhập, chờ TikTok Studio "
            "hiện ra và giữ Chrome mở; sau đó bấm Đăng TikTok.",
        )


class FacebookBrowserConnection:
    """Compatibility wrapper retained for existing callers."""

    def __init__(
        self,
        profile_dir: Path,
        *,
        browser_channel: str = "chrome",
        launcher: Launcher | None = None,
        chrome_executable: Path | None = None,
    ) -> None:
        del browser_channel
        self._manager = ChromeLoginManager(
            profile_dir,
            launcher=launcher,
            chrome_executable=chrome_executable,
        )

    def open_and_check(self) -> BrowserConnectionResult:
        return self._manager.open_facebook()

    def close(self) -> None:
        # Normal Chrome belongs to the user and is never killed by the app.
        return None
