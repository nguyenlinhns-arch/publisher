from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig
from ..secrets import FACEBOOK_TOKEN_NAME, SecretStore
from .media import MediaInspectionError, VideoEditError, find_ffmpeg, find_ffprobe


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    passed: bool
    message: str
    blocking: bool = True


def _directory_check(path: Path, label: str) -> DoctorCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix="doctor_", delete=True):
            pass
        return DoctorCheck(label, True, f"{label}: có thể ghi.")
    except OSError as exc:
        return DoctorCheck(label, False, f"{label}: không thể ghi ({exc}).")


def _database_check(path: Path) -> DoctorCheck:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA integrity_check")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS doctor_probe (id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()
        return DoctorCheck("SQLite", True, "SQLite hoạt động và database có thể ghi.")
    except sqlite3.Error as exc:
        return DoctorCheck("SQLite", False, f"SQLite lỗi: {exc}")


def _ffprobe_check() -> DoctorCheck:
    try:
        executable = find_ffprobe()
        completed = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (MediaInspectionError, OSError, subprocess.TimeoutExpired) as exc:
        return DoctorCheck("ffprobe", False, f"Không chạy được ffprobe: {exc}")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"mã lỗi {completed.returncode}"
        return DoctorCheck("ffprobe", False, f"ffprobe lỗi: {detail}")
    first_line = (completed.stdout.splitlines() or ["ffprobe"])[0]
    return DoctorCheck("ffprobe", True, f"ffprobe hoạt động: {first_line}")


def _ffmpeg_check() -> DoctorCheck:
    try:
        executable = find_ffmpeg()
        completed = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (VideoEditError, OSError, subprocess.TimeoutExpired) as exc:
        return DoctorCheck("ffmpeg", False, f"Không chạy được ffmpeg: {exc}")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"mã lỗi {completed.returncode}"
        return DoctorCheck("ffmpeg", False, f"ffmpeg lỗi: {detail}")
    first_line = (completed.stdout.splitlines() or ["ffmpeg"])[0]
    return DoctorCheck("ffmpeg", True, f"ffmpeg hoạt động: {first_line}")


def _playwright_check() -> DoctorCheck:
    try:
        from playwright.sync_api import sync_playwright

        manager = sync_playwright().start()
        try:
            _ = manager.chromium
        finally:
            manager.stop()
    except Exception as exc:
        return DoctorCheck(
            "Playwright", False, f"Playwright driver không khởi động được: {exc}"
        )
    return DoctorCheck("Playwright", True, "Playwright driver hoạt động.")


def _secret_store_check(store: SecretStore, *, blocking: bool) -> DoctorCheck:
    try:
        token = store.get(FACEBOOK_TOKEN_NAME)
    except Exception as exc:
        return DoctorCheck(
            "Kho bí mật",
            False,
            f"Không đọc được kho bí mật hệ điều hành: {exc}",
            blocking=blocking,
        )
    return DoctorCheck(
        "Kho bí mật",
        bool(token) if blocking else True,
        "Đã tìm thấy Facebook Page token trong kho bí mật."
        if token
        else (
            "Kho bí mật hoạt động nhưng chưa có Facebook Page token."
            if blocking
            else "Kho bí mật có thể truy cập; luồng Chrome không cần Page token."
        ),
        blocking=blocking,
    )


def run_doctor(
    config: AppConfig,
    *,
    include_accounts: bool = True,
    secret_store: SecretStore | None = None,
) -> list[DoctorCheck]:
    checks = [
        DoctorCheck(
            "Python",
            sys.version_info >= (3, 12),
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
        _directory_check(config.media_dir, "Thư mục media"),
        _directory_check(config.logs_dir, "Thư mục log"),
        _directory_check(config.screenshots_dir, "Thư mục ảnh chụp"),
        _database_check(config.database_path),
        _ffprobe_check(),
        _ffmpeg_check(),
        _playwright_check(),
    ]
    for module, label in (("httpx", "HTTP client"), ("keyring", "Keyring")):
        installed = importlib.util.find_spec(module) is not None
        checks.append(
            DoctorCheck(
                label,
                installed,
                f"{label}: " + ("đã cài." if installed else "chưa cài dependency."),
            )
        )

    store = secret_store or SecretStore()
    # Browser publishing does not require a Facebook Page token.  Keep this
    # legacy-store diagnostic informational for upgrades that still contain an
    # old token, but never block normal desktop use.
    checks.append(_secret_store_check(store, blocking=False))
    if include_accounts:
        page_id = config.facebook_page_id.strip()
        checks.append(
            DoctorCheck(
                "Facebook Page ID",
                page_id.isdigit(),
                f"Facebook Page ID: {page_id}."
                if page_id.isdigit()
                else "Facebook Page ID chưa được cấu hình hợp lệ.",
            )
        )
        tiktok_account = config.tiktok_account_id.strip()
        checks.append(
            DoctorCheck(
                "TikTok account",
                bool(tiktok_account),
                f"TikTok đích: {tiktok_account}."
                if tiktok_account
                else "Chưa cấu hình tài khoản TikTok đích.",
            )
        )

    if sys.platform == "win32":
        chrome_candidates = [
            Path(root) / "Google/Chrome/Application/chrome.exe"
            for root in (
                os.environ.get("PROGRAMFILES", ""),
                os.environ.get("PROGRAMFILES(X86)", ""),
                os.environ.get("LOCALAPPDATA", ""),
            )
            if root
        ]
        found = next((path for path in chrome_candidates if path.is_file()), None)
        checks.append(
            DoctorCheck(
                "Google Chrome",
                found is not None,
                f"Google Chrome: {found}"
                if found
                else "Không tìm thấy Google Chrome.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Windows",
                False,
                "Môi trường hiện tại không phải Windows; chỉ dùng để phát triển/kiểm thử.",
                blocking=False,
            )
        )
    return checks


def format_doctor(checks: list[DoctorCheck]) -> str:
    lines = []
    for check in checks:
        symbol = "✓" if check.passed else ("✗" if check.blocking else "!")
        lines.append(f"{symbol} {check.message}")
    blocking_failures = sum(not check.passed and check.blocking for check in checks)
    lines.append(f"Kết quả: {blocking_failures} lỗi chặn.")
    return "\n".join(lines)
