from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .media import probe
from .project import ProjectState

VALID_PROFILES = {
    "TRAVEL_DOCUMENTARY",
    "TALKING_HEAD_EXPERT",
    "EXPLAINER_NEWS",
    "DIRECT_RECRUITMENT",
}
HOOK_ROLES = {"context", "main", "keyword"}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    passed: bool
    duration: float
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
    info: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "duration": self.duration,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "info": [asdict(item) for item in self.info],
        }


def _issue(level: str, code: str, message: str, path: str = "") -> ValidationIssue:
    return ValidationIssue(level=level, code=code, message=message, path=path)


def validate_project(project: ProjectState, *, deep: bool = False) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    info: list[ValidationIssue] = []

    if project.profile not in VALID_PROFILES:
        errors.append(_issue("error", "INVALID_PROFILE", f"Profile không hợp lệ: {project.profile}"))

    duration = round(sum(max(0.0, item.duration) for item in project.timeline), 3)
    if not project.timeline:
        errors.append(_issue("error", "EMPTY_TIMELINE", "Timeline đang trống."))

    if project.target_seconds <= 0:
        errors.append(_issue("error", "INVALID_TARGET", "Thời lượng mục tiêu phải lớn hơn 0."))
    elif duration:
        tolerance = max(2.0, project.target_seconds * 0.08)
        if abs(duration - project.target_seconds) > tolerance:
            warnings.append(
                _issue(
                    "warning",
                    "TARGET_DRIFT",
                    f"Timeline {duration:.1f}s lệch mục tiêu {project.target_seconds:.1f}s.",
                )
            )

    checked_paths: set[str] = set()
    probed: dict[str, Any] = {}
    for index, item in enumerate(project.media):
        path = Path(item.path).expanduser()
        if not path.is_file():
            errors.append(
                _issue(
                    "error",
                    "MISSING_MEDIA",
                    f"Media không tồn tại: {path}",
                    f"media[{index}]",
                )
            )
            continue
        checked_paths.add(str(path.resolve()))
        if deep and item.kind == "video":
            try:
                probed[str(path.resolve())] = probe(path)
            except Exception as exc:
                errors.append(
                    _issue(
                        "error",
                        "MEDIA_PROBE_FAILED",
                        f"Không đọc được media {path.name}: {exc}",
                        f"media[{index}]",
                    )
                )

    total_work = 0.0
    road_reset = 0
    hook_seen: dict[str, int] = {}
    for index, item in enumerate(project.timeline):
        if item.duration <= 0:
            errors.append(
                _issue(
                    "error",
                    "INVALID_CLIP_DURATION",
                    f"Clip {index + 1} có duration <= 0.",
                    f"timeline[{index}]",
                )
            )
        if item.start < 0:
            errors.append(
                _issue(
                    "error",
                    "INVALID_CLIP_START",
                    f"Clip {index + 1} có start âm.",
                    f"timeline[{index}]",
                )
            )
        path = Path(item.path).expanduser()
        if not path.is_file():
            errors.append(
                _issue(
                    "error",
                    "MISSING_TIMELINE_MEDIA",
                    f"Clip timeline thiếu file: {path}",
                    f"timeline[{index}]",
                )
            )
        if item.role in {"work", "admin"}:
            total_work += max(0.0, item.duration)
        if item.role == "road_reset":
            road_reset += 1

        if deep and item.kind == "video" and path.is_file():
            key = str(path.resolve())
            info_obj = probed.get(key)
            if info_obj is None:
                try:
                    info_obj = probe(path)
                    probed[key] = info_obj
                except Exception:
                    info_obj = None
            if info_obj is not None:
                if item.start + item.duration > info_obj.duration + 0.12:
                    errors.append(
                        _issue(
                            "error",
                            "CLIP_OUT_OF_RANGE",
                            (
                                f"Clip {index + 1} dùng đến "
                                f"{item.start + item.duration:.2f}s nhưng nguồn chỉ "
                                f"{info_obj.duration:.2f}s."
                            ),
                            f"timeline[{index}]",
                        )
                    )

    if project.profile == "TRAVEL_DOCUMENTARY" and duration >= 30:
        if road_reset == 0:
            warnings.append(
                _issue(
                    "warning",
                    "TRAVEL_NO_ROAD_RESET",
                    "Travel/Công tác chưa có road reset để chuyển chương.",
                )
            )
        if duration and total_work / duration > 0.45:
            warnings.append(
                _issue(
                    "warning",
                    "WORK_DOMINATES_TRAVEL",
                    "Cảnh công việc/admin đang chiếm quá nhiều thời lượng travel.",
                )
            )

    for index, item in enumerate(project.texts):
        if item.start < 0 or item.end <= item.start:
            errors.append(
                _issue(
                    "error",
                    "INVALID_TEXT_RANGE",
                    f"Text {index + 1} có timecode không hợp lệ.",
                    f"texts[{index}]",
                )
            )
        if duration and item.end > duration + 0.15:
            warnings.append(
                _issue(
                    "warning",
                    "TEXT_AFTER_TIMELINE",
                    f"Text {index + 1} kết thúc sau timeline.",
                    f"texts[{index}]",
                )
            )
        if item.role in HOOK_ROLES:
            hook_seen[item.role] = hook_seen.get(item.role, 0) + 1

    duplicates = [role for role, count in hook_seen.items() if count > 1]
    if duplicates:
        warnings.append(
            _issue(
                "warning",
                "DUPLICATE_HOOK_LAYER",
                "Hook có layer trùng: " + ", ".join(sorted(duplicates)),
            )
        )

    if project.profile == "TRAVEL_DOCUMENTARY":
        missing = HOOK_ROLES - set(hook_seen)
        if project.texts and missing:
            info.append(
                _issue(
                    "info",
                    "HOOK_INCOMPLETE",
                    "Hook 3 tầng chưa đủ: " + ", ".join(sorted(missing)),
                )
            )

    audio_ranges = [
        ("music_gain", project.music_gain, 0.0, 4.0),
        ("voice_gain", project.voice_gain, 0.0, 4.0),
        ("duck_threshold", project.duck_threshold, 0.0001, 1.0),
        ("duck_ratio", project.duck_ratio, 1.0, 20.0),
        ("duck_attack_ms", project.duck_attack_ms, 1.0, 2000.0),
        ("duck_release_ms", project.duck_release_ms, 1.0, 5000.0),
        ("caption_coverage_target", project.caption_coverage_target, 0.10, 1.0),
    ]
    for name, value, low, high in audio_ranges:
        if not low <= float(value) <= high:
            errors.append(
                _issue(
                    "error",
                    "INVALID_SETTING",
                    f"{name} phải nằm trong khoảng {low}–{high}.",
                    name,
                )
            )

    for label, value in (("voiceover", project.voiceover), ("music", project.music)):
        if value and not Path(value).expanduser().is_file():
            errors.append(
                _issue(
                    "error",
                    f"MISSING_{label.upper()}",
                    f"Không tìm thấy {label}: {value}",
                    label,
                )
            )

    for index, item in enumerate(project.sfx):
        if not Path(item.path).expanduser().is_file():
            errors.append(
                _issue(
                    "error",
                    "MISSING_SFX",
                    f"Không tìm thấy SFX: {item.path}",
                    f"sfx[{index}]",
                )
            )

    if project.source_mode in {"NEWS_TEXT", "ARTICLE_URL", "LEGACY_NEWS", "LEGACY_EDITORIAL"}:
        if not project.transcript.strip():
            warnings.append(
                _issue(
                    "warning",
                    "MISSING_TRANSCRIPT",
                    "Nguồn News/Editorial chưa có transcript chuẩn hóa.",
                )
            )
        if not project.story_scenes:
            warnings.append(
                _issue(
                    "warning",
                    "MISSING_STORY_SCENES",
                    "Nguồn News/Editorial chưa lưu story_scenes.",
                )
            )

    if deep:
        for key, info_obj in probed.items():
            if info_obj.height <= info_obj.width:
                info.append(
                    _issue(
                        "info",
                        "LANDSCAPE_REFRAME",
                        f"{Path(key).name} là footage ngang, cần reframe 9:16.",
                        key,
                    )
                )
            if max(info_obj.width, info_obj.height) < 1280:
                warnings.append(
                    _issue(
                        "warning",
                        "LOW_RESOLUTION",
                        f"{Path(key).name} có độ phân giải thấp.",
                        key,
                    )
                )
            if info_obj.fps and info_obj.fps < 23.5:
                warnings.append(
                    _issue(
                        "warning",
                        "LOW_FPS",
                        f"{Path(key).name} chỉ {info_obj.fps:.2f} fps.",
                        key,
                    )
                )

    return ValidationReport(
        passed=not errors,
        duration=duration,
        errors=tuple(errors),
        warnings=tuple(warnings),
        info=tuple(info),
    )
