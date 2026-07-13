from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
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
    trim_end_seconds: float = 6.2
    frame_path: Path | None = None


class VideoEditError(RuntimeError):
    pass


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
    if duration < 3 or duration > 90:
        issues.append(
            MediaIssue("error", "DURATION", "Thời lượng chung phải từ 3 đến 90 giây.")
        )
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
    """Trim and render one immutable 9:16 upload asset for both platforms."""

    source = source.expanduser().resolve()
    if not source.is_file():
        raise VideoEditError(f"Không tìm thấy video gốc: {source}")
    if spec.trim_start_seconds < 0 or spec.trim_end_seconds < 0:
        raise VideoEditError("Thời gian cắt đầu/cuối không được âm.")

    frame = spec.frame_path.expanduser().resolve() if spec.frame_path else None
    if frame is not None and not frame.is_file():
        raise VideoEditError(f"Không tìm thấy khung hình: {frame}")

    source_info = inspect_video(source)
    output_duration = (
        source_info.duration_seconds
        - spec.trim_start_seconds
        - spec.trim_end_seconds
    )
    if output_duration < 3:
        raise VideoEditError(
            "Video còn dưới 3 giây sau khi cắt. Hãy giảm thời gian cắt đầu/cuối."
        )
    if output_duration > 90:
        raise VideoEditError(
            f"Video sau khi cắt còn {output_duration:.1f} giây; cần tối đa 90 giây. "
            "Hãy tăng số giây cắt cuối."
        )

    frame_digest = sha256_file(frame) if frame else "no-frame"
    recipe = json.dumps(
        {
            "source": source_info.sha256,
            "frame": frame_digest,
            "trim_start": round(spec.trim_start_seconds, 3),
            "trim_end": round(spec.trim_end_seconds, 3),
            "size": "1080x1920",
            "fps": 30,
            "codec": "h264-aac-v1",
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
    temporary.unlink(missing_ok=True)
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
    if frame is not None:
        command.extend(["-loop", "1", "-i", str(frame)])

    if source_info.has_audio:
        audio_map = "0:a:0"
    else:
        silence_index = 2 if frame is not None else 1
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        audio_map = f"{silence_index}:a:0"

    base_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,fps=30"
    )
    if frame is None:
        video_filter = f"[0:v]{base_filter},format=yuv420p[v]"
    else:
        video_filter = (
            f"[0:v]{base_filter}[base];"
            "[1:v]scale=1080:1920,format=rgba[frame];"
            "[base][frame]overlay=0:0:format=auto,format=yuv420p[v]"
        )
    command.extend(
        [
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            audio_map,
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
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        temporary.unlink(missing_ok=True)
        raise VideoEditError(f"Không xuất được video: {exc}") from exc
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
