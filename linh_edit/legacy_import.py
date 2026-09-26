from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .media import probe_duration
from .news_ingest import NewsScene, apply_news_scenes, build_transcript, parse_news_content
from .project import ProjectState
from .tools import resolve_asset


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _resolve_legacy_image(base: Path, value: Any) -> str | None:
    candidate = ""
    if isinstance(value, str):
        candidate = value
    elif isinstance(value, dict):
        candidate = str(
            value.get("src")
            or value.get("path")
            or value.get("file")
            or value.get("image")
            or ""
        )
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_absolute():
        path = (base / path).resolve()
    return str(path) if path.is_file() else None


def _legacy_images(path: Path, payload: dict[str, Any]) -> list[str]:
    base = path.parent
    result: list[str] = []
    seen: set[str] = set()

    for raw in payload.get("scenes", []):
        if not isinstance(raw, dict):
            continue
        image = _resolve_legacy_image(base, raw.get("image"))
        if image and image not in seen:
            seen.add(image)
            result.append(image)

    for folder in (
        base / "assets" / "article_images",
        base / "assets" / "news",
        base / "assets" / "images",
    ):
        if not folder.is_dir():
            continue
        for item in sorted(folder.iterdir()):
            if item.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                continue
            value = str(item.resolve())
            if value not in seen:
                seen.add(value)
                result.append(value)

    if not result:
        try:
            result.append(str(resolve_asset("assets/nen.png").resolve()))
        except Exception:
            pass
    return result


def _legacy_title(payload: dict[str, Any], scenes: list[NewsScene]) -> str:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    return str(
        project.get("title")
        or project.get("name")
        or (scenes[0].title if scenes else "")
        or project.get("slug")
        or "Video cũ"
    )


def import_legacy_script(path: Path, project: ProjectState) -> ProjectState:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("script.json cũ phải là object JSON.")

    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("script.json cũ không có danh sách scenes.")

    scenes = parse_news_content(json.dumps(payload, ensure_ascii=False))
    images = _legacy_images(path, payload)
    if not images:
        raise ValueError("Không tìm thấy ảnh cũ và cũng không có nền Linh Edit để thay thế.")

    scene_types = {
        str(item.get("type") or "").lower()
        for item in raw_scenes
        if isinstance(item, dict)
    }
    source_mode = "LEGACY_NEWS" if scene_types == {"news"} else "LEGACY_EDITORIAL"

    expected_transcript = build_transcript(scenes)
    total_seconds: float | None = None
    transcript_path = path.parent / "transcript.txt"
    voice_path = path.parent / "assets" / "voice.mp3"
    if transcript_path.is_file():
        current = transcript_path.read_text(encoding="utf-8-sig")
        if _normalized_text(current) == _normalized_text(expected_transcript) and voice_path.is_file():
            try:
                total_seconds = probe_duration(voice_path)
                project.voiceover = str(voice_path.resolve())
            except Exception:
                total_seconds = None

    music_path = path.parent / "assets" / "background_music.mp3"
    if music_path.is_file():
        project.music = str(music_path.resolve())

    apply_news_scenes(
        project,
        scenes,
        images=images,
        total_seconds=total_seconds,
        source_mode=source_mode,
        source_text=path.read_text(encoding="utf-8-sig"),
        title=_legacy_title(payload, scenes),
    )
    # apply_news_scenes rebuilds the canonical transcript from the old scene narration.
    project.dirty = True
    return project
