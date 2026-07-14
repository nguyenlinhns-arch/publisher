from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mxh_publisher.services.media import (
    VideoEditSpec,
    VideoInfo,
    default_frame_path,
    inspect_video,
    render_social_video,
    sha256_file,
)

from .config import EditorConfig


TRIM_START_SECONDS = 6.2
TRIM_END_SECONDS = 4.0


@dataclass(frozen=True, slots=True)
class RenderedVideo:
    path: Path
    info: VideoInfo


@dataclass(frozen=True, slots=True)
class BatchVideoItem:
    source: Path
    title: str


@dataclass(frozen=True, slots=True)
class BatchRenderOutcome:
    item: BatchVideoItem
    rendered: RenderedVideo | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.rendered is not None and self.error is None


def safe_filename(value: str, *, fallback: str = "video_da_sua") -> str:
    cleaned = unicodedata.normalize("NFC", " ".join(value.split()))
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", cleaned)
    cleaned = cleaned.strip(" .-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:90].rstrip(" .-") or fallback


def _unique_destination(output_dir: Path, title: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{stamp}_{safe_filename(title)}"
    candidate = output_dir / f"{base}.mp4"
    number = 2
    while candidate.exists():
        candidate = output_dir / f"{base}_{number}.mp4"
        number += 1
    return candidate


def render_video(
    config: EditorConfig,
    source: Path,
    title: str,
    *,
    frame_path: Path | None = None,
) -> RenderedVideo:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy video gốc: {source}")
    normalized_title = " ".join(title.split()) or source.stem
    spec = VideoEditSpec(
        trim_start_seconds=TRIM_START_SECONDS,
        trim_end_seconds=TRIM_END_SECONDS,
        frame_path=frame_path or default_frame_path(),
        title=normalized_title,
    )
    cached = render_social_video(source, config.cache_dir, spec)
    destination = _unique_destination(config.output_dir, normalized_title)
    temporary = destination.with_suffix(".partial.mp4")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(cached.path, temporary)
        if sha256_file(temporary) != cached.sha256:
            raise OSError("Video bị thay đổi trong lúc lưu thành phẩm.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return RenderedVideo(path=destination, info=inspect_video(destination))


def build_batch_items(sources: Iterable[Path]) -> tuple[BatchVideoItem, ...]:
    """Create a stable, de-duplicated batch using each filename as its title."""

    items: list[BatchVideoItem] = []
    seen: set[str] = set()
    for source in sources:
        resolved = source.expanduser().resolve()
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        items.append(BatchVideoItem(source=resolved, title=resolved.stem))
    return tuple(items)


def render_video_batch(
    config: EditorConfig,
    items: Sequence[BatchVideoItem],
    *,
    frame_path: Path | None = None,
    on_progress: Callable[[int, int, BatchRenderOutcome], None] | None = None,
) -> tuple[BatchRenderOutcome, ...]:
    """Render a batch sequentially and keep going after an individual failure."""

    outcomes: list[BatchRenderOutcome] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        try:
            rendered = render_video(
                config,
                item.source,
                item.title,
                frame_path=frame_path,
            )
            outcome = BatchRenderOutcome(item=item, rendered=rendered)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            outcome = BatchRenderOutcome(item=item, error=message)
        outcomes.append(outcome)
        if on_progress is not None:
            on_progress(index, total, outcome)
    return tuple(outcomes)


def list_rendered_videos(config: EditorConfig) -> list[Path]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        (path for path in config.output_dir.glob("*.mp4") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def delete_rendered_video(config: EditorConfig, path: Path) -> None:
    target = path.expanduser().resolve()
    output_root = config.output_dir.resolve()
    if target.parent != output_root or target.suffix.lower() != ".mp4":
        raise ValueError("Chỉ được xóa video MP4 trong thư mục thành phẩm.")
    if not target.is_file():
        raise FileNotFoundError(f"Không tìm thấy video thành phẩm: {target}")
    target.unlink()


def open_in_system(path: Path) -> None:
    target = path.expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(target)
    if sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    command = ["open", str(target)] if sys.platform == "darwin" else ["xdg-open", str(target)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
