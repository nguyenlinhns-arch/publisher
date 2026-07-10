from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .media import MediaInspectionError, VideoInfo, inspect_video, sha256_file


@dataclass(frozen=True, slots=True)
class CheckResult:
    passed: bool
    code: str
    message: str
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class DryRunReport:
    checks: tuple[CheckResult, ...]
    video_info: VideoInfo | None = None

    @property
    def ready(self) -> bool:
        return not any(not check.passed and check.blocking for check in self.checks)

    def as_text(self) -> str:
        lines = ["DRY-RUN: " + ("ĐỦ ĐIỀU KIỆN" if self.ready else "CHƯA ĐỦ ĐIỀU KIỆN")]
        for check in self.checks:
            marker = "✓" if check.passed else ("✗" if check.blocking else "!")
            lines.append(f"{marker} {check.message}")
        return "\n".join(lines)


def run_dry_run(
    *,
    video_path: Path,
    expected_sha256: str,
    caption: str,
    hashtags: str,
    scheduled_at_utc: datetime,
    approved: bool,
    minimum_lead_minutes: int = 30,
    caption_soft_limit: int = 2200,
    ffprobe_path: Path | None = None,
) -> DryRunReport:
    checks: list[CheckResult] = []
    video_info: VideoInfo | None = None
    checks.append(
        CheckResult(
            approved,
            "APPROVAL",
            "Nội dung đã được duyệt." if approved else "Nội dung chưa được duyệt.",
        )
    )

    if not video_path.is_file():
        checks.append(CheckResult(False, "VIDEO_MISSING", "Không tìm thấy tệp video."))
    else:
        actual_sha = sha256_file(video_path)
        checks.append(
            CheckResult(
                actual_sha == expected_sha256,
                "VIDEO_HASH",
                "Video không thay đổi sau khi duyệt."
                if actual_sha == expected_sha256
                else "Video đã thay đổi sau khi duyệt; cần duyệt lại.",
            )
        )
        try:
            video_info = inspect_video(video_path, ffprobe_path)
            checks.extend(
                CheckResult(
                    issue.severity != "error",
                    issue.code,
                    issue.message,
                    blocking=issue.severity == "error",
                )
                for issue in video_info.issues
            )
            if not video_info.issues:
                checks.append(
                    CheckResult(True, "VIDEO_TECHNICAL", "Thông số video hợp lệ.")
                )
        except MediaInspectionError as exc:
            checks.append(CheckResult(False, "FFPROBE", str(exc)))

    clean_caption = caption.strip()
    checks.append(
        CheckResult(
            bool(clean_caption),
            "CAPTION",
            "Caption đã có nội dung." if clean_caption else "Caption đang để trống.",
        )
    )
    full_text = (clean_caption + " " + hashtags.strip()).strip()
    checks.append(
        CheckResult(
            len(full_text) <= caption_soft_limit,
            "CAPTION_LENGTH",
            f"Caption và hashtag dài {len(full_text)}/{caption_soft_limit} ký tự.",
        )
    )
    if scheduled_at_utc.tzinfo is None:
        checks.append(CheckResult(False, "TIMEZONE", "Thời gian đăng chưa có múi giờ."))
    else:
        now = datetime.now(UTC)
        earliest = now + timedelta(minutes=minimum_lead_minutes)
        checks.append(
            CheckResult(
                scheduled_at_utc.astimezone(UTC) >= earliest,
                "SCHEDULE_LEAD",
                f"Thời gian đăng cách hiện tại ít nhất {minimum_lead_minutes} phút.",
            )
        )
    return DryRunReport(tuple(checks), video_info)
