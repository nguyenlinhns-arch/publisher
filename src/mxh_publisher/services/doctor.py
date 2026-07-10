from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig
from .media import MediaInspectionError, find_ffprobe


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


def run_doctor(config: AppConfig) -> list[DoctorCheck]:
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
    ]
    try:
        ffprobe = find_ffprobe()
        checks.append(DoctorCheck("ffprobe", True, f"Đã tìm thấy ffprobe: {ffprobe}"))
    except MediaInspectionError as exc:
        checks.append(DoctorCheck("ffprobe", False, str(exc)))

    for module, label in (
        ("httpx", "HTTP client"),
        ("playwright", "Playwright"),
        ("keyring", "Kho bí mật"),
    ):
        installed = importlib.util.find_spec(module) is not None
        checks.append(
            DoctorCheck(
                label,
                installed,
                f"{label}: " + ("đã cài." if installed else "chưa cài dependency."),
            )
        )

    if sys.platform == "win32":
        edge_candidates = [
            Path(os.environ.get("PROGRAMFILES(X86)", ""))
            / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", ""))
            / "Microsoft/Edge/Application/msedge.exe",
        ]
        found = next((path for path in edge_candidates if path.is_file()), None)
        checks.append(
            DoctorCheck(
                "Microsoft Edge",
                found is not None,
                f"Microsoft Edge: {found}"
                if found
                else "Không tìm thấy Microsoft Edge.",
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
