from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class MediaIssue:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class VideoInfo:
    path: Path
    sha256: str
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    has_audio: bool
    issues: tuple[MediaIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class MediaInspectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VideoEditSpec:
    trim_start_seconds: float = 6.2
    trim_end_seconds: float = 4.0
    frame_path: Path | None = None
    intro_sound_path: Path | None = None
    title: str = ""


class VideoEditError(RuntimeError):
    pass


VIDEO_TOP = 360
VIDEO_HEIGHT = 608
WINDOWS_CREATE_NO_WINDOW = 0x08000000


def subprocess_creation_flags(platform: str | None = None) -> int:
    """Prevent bundled FFmpeg tools from opening CMD windows on Windows."""

    current_platform = platform if platform is not None else sys.platform
    return WINDOWS_CREATE_NO_WINDOW if current_platform == "win32" else 0


def default_frame_path() -> Path:
    """Return the bundled blue 1080x1920 frame supplied for this project."""

    if getattr(sys, "frozen", False):
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        runtime_root = Path(__file__).resolve().parents[3]
    frame = runtime_root / "assets" / "nen.png"
    if not frame.is_file():
        raise VideoEditError(f"Thiếu khung nền mặc định: {frame}")
    return frame.resolve()


def default_fonts_dir() -> Path:
    """Return the bundled fonts used by the news-video template."""

    if getattr(sys, "frozen", False):
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        runtime_root = Path(__file__).resolve().parents[3]
    fonts = runtime_root / "assets" / "fonts"
    required = (
        fonts / "Oswald-Bold.ttf",
        fonts / "BeVietnamPro-SemiBold.ttf",
    )
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise VideoEditError("Thiếu font chữ đóng gói: " + ", ".join(missing))
    return fonts.resolve()


def default_intro_sound_path() -> Path:
    """Return the short sound that replaces the opening audio of every video."""

    if getattr(sys, "frozen", False):
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        runtime_root = Path(__file__).resolve().parents[3]
    sound = runtime_root / "assets" / "sound.mp3"
    if not sound.is_file() or sound.stat().st_size == 0:
        raise VideoEditError(f"Thiếu âm thanh mở đầu hợp lệ: {sound}")
    return sound.resolve()


def _wrapped_video_title(value: str) -> str:
    cleaned = " ".join(value.replace("{", "（").replace("}", "）").split())
    cleaned = cleaned.replace("\\", "／").upper()
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    if "|" in cleaned or "-" in cleaned:
        manual_parts = cleaned.replace("|", "-").split("-")
        lines = []
        for part in manual_parts:
            lines.extend(
                textwrap.wrap(
                    part.strip(),
                    width=32,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
    else:
        words = cleaned.split()
        action_words = {
            "GẶP",
            "TỔ",
            "TUYÊN",
            "BIỂU",
            "TRAO",
            "ĐÓN",
            "KHEN",
            "KHAI",
            "PHÁT",
            "THĂM",
            "CHÚC",
            "CÔNG",
        }
        action_at = next(
            (index for index, word in enumerate(words[2:7], start=2) if word in action_words),
            None,
        )
        number_at = next(
            (index for index, word in enumerate(words) if any(ch.isdigit() for ch in word)),
            None,
        )
        if action_at is not None and number_at is not None and action_at < number_at:
            lines = [
                " ".join(words[:action_at]),
                " ".join(words[action_at:number_at]),
                " ".join(words[number_at:]),
            ]
        else:
            lines = textwrap.wrap(
                cleaned,
                width=34,
                break_long_words=False,
                break_on_hyphens=False,
            ) or ["NỘI DUNG VIDEO"]
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = textwrap.shorten(lines[-1], width=26, placeholder="…")
    return r"\N".join(lines)


def _ass_time(seconds: float) -> str:
    total_centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def _title_font_size(wrapped_title: str) -> int:
    """Keep short news headlines bold while preventing long lines overflowing."""

    longest_line = max((len(line) for line in wrapped_title.split(r"\N")), default=0)
    if longest_line <= 18:
        return 128
    if longest_line <= 24:
        return 112
    if longest_line <= 30:
        return 96
    return 82


def _write_title_ass(path: Path, title: str, duration_seconds: float) -> None:
    end = _ass_time(duration_seconds)
    wrapped = _wrapped_video_title(title)
    title_font_size = _title_font_size(wrapped)
    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Title,Oswald,96,&H00FFFFFF,&H00FFFFFF,"
            "&H00000000,&H50000000,-1,0,0,0,100,100,0,0,1,5,1,8,55,55,0,1",
            "Style: Brand,Be Vietnam Pro SemiBold,38,&H00FFFFFF,&H00FFFFFF,"
            "&H00000000,&H50000000,-1,0,0,0,100,100,0,0,1,3,1,8,40,40,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text",
            f"Dialogue: 0,0:00:00.00,{end},Title,,0,0,0,,"
            rf"{{\an8\pos(540,1040)\fs{title_font_size}}}{wrapped}",
            f"Dialogue: 0,0:00:00.00,{end},Brand,,0,0,0,,"
            r"{\an8\pos(540,1510)}Thầy Linh - Tuyển Thợ Mỏ",
        ]
    )
    path.write_text(content, encoding="utf-8-sig")


def _ffmpeg_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_fraction(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" not in value:
        return float(value)
    numerator, denominator = value.split("/", 1)
    denominator_value = float(denominator)
    return float(numerator) / denominator_value if denominator_value else 0.0


def find_ffprobe(explicit_path: Path | None = None) -> str:
    candidates = [explicit_path] if explicit_path else []
    if getattr(sys, "frozen", False):
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        runtime_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            runtime_root / "bin" / "ffprobe.exe",
            Path(sys.executable).resolve().parent / "bin" / "ffprobe.exe",
            Path("bin/ffprobe.exe"),
            Path("ffprobe"),
        ]
    )
    for candidate in candidates:
        if candidate is None:
            continue
        if str(candidate) == "ffprobe":
            resolved = shutil.which("ffprobe")
            if resolved:
                return resolved
        elif candidate.exists():
            return str(candidate.resolve())
    raise MediaInspectionError(
        "Không tìm thấy ffprobe. Hãy cài FFmpeg hoặc đặt ffprobe.exe trong thư mục bin."
    )


def find_ffmpeg(explicit_path: Path | None = None) -> str:
    candidates = [explicit_path] if explicit_path else []
    if getattr(sys, "frozen", False):
        runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        runtime_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            runtime_root / "bin" / "ffmpeg.exe",
            Path(sys.executable).resolve().parent / "bin" / "ffmpeg.exe",
            Path("bin/ffmpeg.exe"),
            Path("ffmpeg"),
        ]
    )
    for candidate in candidates:
        if candidate is None:
            continue
        if str(candidate) == "ffmpeg":
            resolved = shutil.which("ffmpeg")
            if resolved:
                return resolved
        elif candidate.exists():
            return str(candidate.resolve())
    raise VideoEditError(
        "Không tìm thấy ffmpeg. Hãy cài FFmpeg hoặc đặt ffmpeg.exe trong thư mục bin."
    )


def probe_media_duration(path: Path, ffprobe_path: Path | None = None) -> float:
    """Read a media duration without requiring a video stream."""

    target = path.expanduser().resolve()
    if not target.is_file():
        raise MediaInspectionError(f"Không tìm thấy tệp âm thanh: {target}")
    command = [
        find_ffprobe(ffprobe_path),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_entries",
        "format=duration",
        str(target),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            creationflags=subprocess_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaInspectionError(f"Không đọc được thời lượng âm thanh: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "ffprobe trả về lỗi không xác định."
        raise MediaInspectionError(detail)
    try:
        duration = float(json.loads(completed.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaInspectionError("Không đọc được thời lượng âm thanh.") from exc
    if duration <= 0:
        raise MediaInspectionError("Âm thanh mở đầu có thời lượng không hợp lệ.")
    return duration


def inspect_video(path: Path, ffprobe_path: Path | None = None) -> VideoInfo:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise MediaInspectionError(f"Không tìm thấy video: {path}")

    executable = find_ffprobe(ffprobe_path)
    command = [
        executable,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            creationflags=subprocess_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaInspectionError(f"Không chạy được ffprobe: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "ffprobe trả về lỗi không xác định."
        raise MediaInspectionError(detail)

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaInspectionError("ffprobe trả về dữ liệu không hợp lệ.") from exc

    streams = payload.get("streams", [])
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    audio = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    if video is None:
        raise MediaInspectionError("Tệp không có luồng hình ảnh.")

    duration = float(
        payload.get("format", {}).get("duration") or video.get("duration") or 0
    )
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    fps = _parse_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    video_codec = str(video.get("codec_name") or "unknown").lower()
    audio_codec = str(audio.get("codec_name") or "unknown").lower() if audio else None
    size_bytes = path.stat().st_size

    issues: list[MediaIssue] = []
    if path.suffix.lower() != ".mp4":
        issues.append(
            MediaIssue("error", "FORMAT_NOT_MP4", "Bản V1 chỉ nhận video MP4.")
        )
    if video_codec != "h264":
        issues.append(MediaIssue("error", "VIDEO_CODEC", "Video phải dùng H.264."))
    if audio is None:
        issues.append(MediaIssue("error", "NO_AUDIO", "Video không có âm thanh."))
    elif audio_codec != "aac":
        issues.append(MediaIssue("error", "AUDIO_CODEC", "Âm thanh phải dùng AAC."))
    if width < 540 or height < 960 or width >= height:
        issues.append(
            MediaIssue("error", "RESOLUTION", "Video phải dọc, tối thiểu 540×960.")
        )
    elif abs((width / height) - (9 / 16)) > 0.02:
        issues.append(MediaIssue("error", "ASPECT_RATIO", "Video phải có tỷ lệ 9:16."))
    if not (24 <= fps <= 60):
        issues.append(
            MediaIssue("error", "FPS", "Tốc độ khung hình phải từ 24 đến 60 fps.")
        )
    if size_bytes > 4 * 1024**3:
        issues.append(
            MediaIssue("error", "FILE_SIZE", "Dung lượng video vượt quá 4 GB.")
        )
    if (width, height) != (1080, 1920):
        issues.append(
            MediaIssue(
                "warning", "RESOLUTION_RECOMMENDED", "Khuyến nghị xuất 1080×1920."
            )
        )
    if not (29.5 <= fps <= 30.5):
        issues.append(
            MediaIssue("warning", "FPS_RECOMMENDED", "Khuyến nghị xuất 30 fps.")
        )

    return VideoInfo(
        path=path,
        sha256=sha256_file(path),
        size_bytes=size_bytes,
        duration_seconds=duration,
        width=width,
        height=height,
        fps=fps,
        video_codec=video_codec,
        audio_codec=audio_codec,
        has_audio=audio is not None,
        issues=tuple(issues),
    )


def ingest_video(source: Path, media_dir: Path, sha256: str | None = None) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    digest = sha256 or sha256_file(source)
    media_dir.mkdir(parents=True, exist_ok=True)
    destination = media_dir / f"{digest[:16]}_{source.name}"
    if destination.exists():
        if sha256_file(destination) != digest:
            raise MediaInspectionError(
                f"Tệp đích đã tồn tại nhưng nội dung khác: {destination}"
            )
        return destination
    temporary = destination.with_suffix(destination.suffix + ".partial")
    shutil.copy2(source, temporary)
    if sha256_file(temporary) != digest:
        temporary.unlink(missing_ok=True)
        raise MediaInspectionError("Video bị thay đổi trong lúc sao chép.")
    temporary.replace(destination)
    return destination


def render_social_video(
    source: Path,
    output_dir: Path,
    spec: VideoEditSpec,
    *,
    ffmpeg_path: Path | None = None,
) -> VideoInfo:
    """Trim and render one immutable 9:16 video asset."""

    source = source.expanduser().resolve()
    if not source.is_file():
        raise VideoEditError(f"Không tìm thấy video gốc: {source}")
    if spec.trim_start_seconds < 0 or spec.trim_end_seconds < 0:
        raise VideoEditError("Thời gian cắt đầu/cuối không được âm.")

    frame = (
        spec.frame_path.expanduser().resolve()
        if spec.frame_path
        else default_frame_path()
    )
    if not frame.is_file():
        raise VideoEditError(f"Không tìm thấy khung hình: {frame}")
    intro_sound = (
        spec.intro_sound_path.expanduser().resolve()
        if spec.intro_sound_path
        else default_intro_sound_path()
    )
    if not intro_sound.is_file() or intro_sound.stat().st_size == 0:
        raise VideoEditError(f"Không tìm thấy âm thanh mở đầu: {intro_sound}")

    source_info = inspect_video(source)
    output_duration = (
        source_info.duration_seconds
        - spec.trim_start_seconds
        - spec.trim_end_seconds
    )
    if output_duration <= 0:
        raise VideoEditError(
            "Thời gian cắt đầu/cuối đã vượt toàn bộ thời lượng video."
        )

    frame_digest = sha256_file(frame)
    intro_sound_digest = sha256_file(intro_sound)
    intro_sound_duration = min(probe_media_duration(intro_sound), output_duration)
    fonts_dir = default_fonts_dir()
    font_digest = hashlib.sha256(
        "".join(
            sha256_file(path)
            for path in (
                fonts_dir / "Oswald-Bold.ttf",
                fonts_dir / "BeVietnamPro-SemiBold.ttf",
            )
        ).encode("ascii")
    ).hexdigest()
    recipe = json.dumps(
        {
            "source": source_info.sha256,
            "frame": frame_digest,
            "fonts": font_digest,
            "intro_sound": intro_sound_digest,
            "intro_sound_duration": round(intro_sound_duration, 3),
            "trim_start": round(spec.trim_start_seconds, 3),
            "trim_end": round(spec.trim_end_seconds, 3),
            "title": " ".join(spec.title.split()),
            "size": "1080x1920",
            "fps": 30,
            "layout": "standalone-blue-oswald-news-sound-v6",
            "codec": "h264-aac-v2",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    recipe_digest = hashlib.sha256(recipe.encode("utf-8")).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"edited_{recipe_digest[:24]}.mp4"
    if destination.is_file():
        existing = inspect_video(destination)
        if existing.is_valid:
            return existing

    executable = find_ffmpeg(ffmpeg_path)
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    title_ass = output_dir / f"title_{recipe_digest[:24]}.ass"
    temporary.unlink(missing_ok=True)
    _write_title_ass(title_ass, spec.title or source.stem, output_duration)
    command = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{spec.trim_start_seconds:.3f}",
        "-i",
        str(source),
    ]
    command.extend(["-loop", "1", "-i", str(frame)])
    intro_sound_index = 2
    command.extend(["-i", str(intro_sound)])

    if source_info.has_audio:
        source_audio_map = "0:a:0"
    else:
        silence_index = 3
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        source_audio_map = f"{silence_index}:a:0"

    video_scale = (
        f"scale=1080:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop=1080:{VIDEO_HEIGHT},fps=30"
    )
    background_filter = "[1:v]scale=1080:1920,format=rgba[background]"
    ass_path = _ffmpeg_filter_path(title_ass)
    fonts_path = _ffmpeg_filter_path(fonts_dir)
    video_filter = (
        f"[0:v]{video_scale}[video];"
        f"{background_filter};"
        f"[background][video]overlay=0:{VIDEO_TOP}:shortest=1[layout];"
        f"[layout]ass=filename='{ass_path}':fontsdir='{fonts_path}',format=yuv420p[v]"
    )
    intro_audio_filter = (
        f"[{intro_sound_index}:a:0]aresample=48000,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
        f"atrim=duration={intro_sound_duration:.3f},asetpts=PTS-STARTPTS[introa]"
    )
    remaining_audio_duration = output_duration - intro_sound_duration
    if remaining_audio_duration > 0:
        main_audio_filter = (
            f"[{source_audio_map}]aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
            f"atrim=start={intro_sound_duration:.3f}:"
            f"duration={remaining_audio_duration:.3f},asetpts=PTS-STARTPTS[maina];"
            "[introa][maina]concat=n=2:v=0:a=1[a]"
        )
        audio_filter = intro_audio_filter + ";" + main_audio_filter
    else:
        audio_filter = intro_audio_filter + ";[introa]anull[a]"
    combined_filter = video_filter + ";" + audio_filter
    command.extend(
        [
            "-filter_complex",
            combined_filter,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{output_duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            "-shortest",
            str(temporary),
        ]
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
            check=False,
            creationflags=subprocess_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        temporary.unlink(missing_ok=True)
        title_ass.unlink(missing_ok=True)
        raise VideoEditError(f"Không xuất được video: {exc}") from exc
    title_ass.unlink(missing_ok=True)
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        detail = completed.stderr.strip() or "ffmpeg trả về lỗi không xác định."
        raise VideoEditError("Không xuất được video:\n" + detail[-2000:])

    try:
        rendered = inspect_video(temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if not rendered.is_valid:
        temporary.unlink(missing_ok=True)
        errors = "; ".join(
            issue.message for issue in rendered.issues if issue.severity == "error"
        )
        raise VideoEditError("Video sau khi xuất chưa đạt chuẩn: " + errors)
    temporary.replace(destination)
    return inspect_video(destination)
