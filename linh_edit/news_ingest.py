from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .project import MediaItem, ProjectState, TextItem


@dataclass(frozen=True, slots=True)
class NewsScene:
    title: str
    voice_text: str
    summary: str
    badge: str = ""
    caption: str = ""
    role: str = "detail"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _words(value: str) -> list[str]:
    return [item for item in re.split(r"\s+", _clean(value)) if item]


def _shorten_words(value: str, maximum: int) -> str:
    words = _words(value)
    if len(words) <= maximum:
        return " ".join(words)
    return " ".join(words[:maximum]).rstrip(" ,.;:—-") + "…"


def _sentences(value: str) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [part.strip(" \t-–—") for part in parts if part.strip(" \t-–—")]


def _title_from_text(value: str) -> str:
    title = _shorten_words(value, 9).rstrip(".!?…")
    return title.upper() if title else "TIN MỚI"


def _summary_from_text(value: str) -> str:
    sentences = _sentences(value)
    source = sentences[0] if sentences else value
    return _shorten_words(source, 18)


def _normalize_scene(raw: Any, index: int) -> NewsScene:
    if isinstance(raw, str):
        voice = _clean(raw)
        if not voice:
            raise ValueError(f"Cảnh {index} không có nội dung.")
        return NewsScene(
            title=_title_from_text(voice),
            voice_text=voice,
            summary=_summary_from_text(voice),
        )
    if not isinstance(raw, dict):
        raise ValueError(f"Cảnh {index} phải là object hoặc chuỗi.")

    voice = _clean(
        raw.get("voice_text")
        or raw.get("narration")
        or raw.get("voice")
        or raw.get("text")
        or raw.get("summary")
        or raw.get("title")
    )
    if not voice:
        raise ValueError(f"Cảnh {index} thiếu voice_text/nội dung.")

    title = _clean(raw.get("title") or raw.get("headline")) or _title_from_text(voice)
    summary = _clean(raw.get("summary") or raw.get("caption")) or _summary_from_text(voice)
    badge = _clean(raw.get("badge") or raw.get("kicker") or raw.get("context"))
    caption = _clean(raw.get("caption"))
    role = _clean(raw.get("role")) or "detail"
    return NewsScene(
        title=_shorten_words(title, 12),
        voice_text=voice,
        summary=_shorten_words(summary, 22),
        badge=_shorten_words(badge, 6),
        caption=_shorten_words(caption, 20),
        role=role,
    )


def _plain_text_scenes(text: str, minimum_scenes: int = 0) -> list[NewsScene]:
    sentences = _sentences(text)
    if not sentences:
        raise ValueError("Nội dung tin đang trống.")

    groups: list[str] = []
    current: list[str] = []
    current_words = 0
    target_words = 34

    for sentence in sentences:
        count = max(1, len(_words(sentence)))
        if current and current_words + count > 48:
            groups.append(" ".join(current))
            current = []
            current_words = 0
        current.append(sentence)
        current_words += count
        if current_words >= target_words:
            groups.append(" ".join(current))
            current = []
            current_words = 0
    if current:
        groups.append(" ".join(current))

    if len(groups) == 1 and len(_words(groups[0])) > 55:
        words = _words(groups[0])
        groups = [
            " ".join(words[start : start + 38])
            for start in range(0, len(words), 38)
        ]

    wanted = max(1, minimum_scenes)
    while len(groups) < wanted:
        longest_index = max(range(len(groups)), key=lambda i: len(_words(groups[i])))
        words = _words(groups[longest_index])
        if len(words) < 16:
            break
        middle = len(words) // 2
        groups[longest_index : longest_index + 1] = [
            " ".join(words[:middle]),
            " ".join(words[middle:]),
        ]

    groups = groups[:12]
    return [
        NewsScene(
            title=_title_from_text(group),
            voice_text=group,
            summary=_summary_from_text(group),
        )
        for group in groups
    ]


def parse_news_content(text: str, *, minimum_scenes: int = 0) -> list[NewsScene]:
    normalized = text.lstrip("\ufeff").strip()
    if not normalized:
        raise ValueError("Nội dung tin đang trống.")

    payload: Any | None = None
    if normalized[:1] in {"{", "["}:
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            payload = None

    if payload is None:
        return _plain_text_scenes(normalized, minimum_scenes)

    if isinstance(payload, dict):
        raw_scenes = payload.get("scenes")
        if raw_scenes is None:
            raw_scenes = [payload]
    elif isinstance(payload, list):
        raw_scenes = payload
    else:
        raise ValueError("JSON tin tức phải là object hoặc danh sách cảnh.")

    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("JSON cần có ít nhất một cảnh.")

    scenes = [_normalize_scene(item, index + 1) for index, item in enumerate(raw_scenes[:40])]
    if minimum_scenes and len(scenes) < minimum_scenes:
        expanded = _plain_text_scenes(
            " ".join(scene.voice_text for scene in scenes),
            minimum_scenes,
        )
        if len(expanded) > len(scenes):
            scenes = expanded
    return scenes


def build_transcript(scenes: Sequence[NewsScene]) -> str:
    return "\n\n".join(scene.voice_text.strip() for scene in scenes if scene.voice_text.strip()).strip() + "\n"


def allocate_scene_seconds(
    scenes: Sequence[NewsScene],
    total_seconds: float,
) -> list[float]:
    if not scenes:
        return []
    total = max(0.5 * len(scenes), float(total_seconds))
    weights = []
    for scene in scenes:
        punctuation_bonus = min(8, sum(scene.voice_text.count(mark) for mark in ",.;:!?…"))
        weights.append(max(6, len(_words(scene.voice_text)) + punctuation_bonus * 0.35))
    weight_sum = sum(weights) or float(len(scenes))
    raw = [total * weight / weight_sum for weight in weights]

    # Keep each scene visible while preserving exact total duration.
    minimum = 1.2 if total >= 1.2 * len(scenes) else total / len(scenes)
    adjusted = [max(minimum, value) for value in raw]
    scale = total / sum(adjusted)
    adjusted = [round(value * scale, 3) for value in adjusted]
    drift = round(total - sum(adjusted), 3)
    adjusted[-1] = max(0.2, round(adjusted[-1] + drift, 3))
    return adjusted


def _image_paths(project: ProjectState, explicit: Iterable[str] | None = None) -> list[str]:
    candidates = [str(Path(item).expanduser().resolve()) for item in (explicit or [])]
    if not candidates:
        candidates = [
            str(Path(item.path).expanduser().resolve())
            for item in project.media
            if item.kind == "image"
        ]
    result: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    if not result:
        raise ValueError("News/Editorial cần ít nhất một ảnh.")
    return result


def _story_payload(scenes: Sequence[NewsScene]) -> list[dict[str, str]]:
    return [asdict(scene) for scene in scenes]


def _hook_keyword(title: str) -> str:
    return _shorten_words(title, 4).upper()


def apply_news_scenes(
    project: ProjectState,
    scenes: Sequence[NewsScene],
    *,
    images: Iterable[str] | None = None,
    total_seconds: float | None = None,
    source_mode: str = "NEWS_TEXT",
    source_text: str = "",
    source_url: str = "",
    title: str | None = None,
) -> ProjectState:
    if not scenes:
        raise ValueError("Không có cảnh để tạo timeline.")

    image_paths = _image_paths(project, images)
    if total_seconds is None:
        default_total = max(12.0, min(90.0, len(scenes) * 7.0))
        total_seconds = min(max(10.0, project.target_seconds), default_total)
    durations = allocate_scene_seconds(scenes, total_seconds)

    project.profile = "EXPLAINER_NEWS"
    project.title = _clean(title) or project.title or scenes[0].title
    project.target_seconds = round(sum(durations), 3)
    project.source_mode = source_mode
    project.source_text = source_text
    project.source_url = source_url
    project.transcript = build_transcript(scenes)
    project.story_scenes = _story_payload(scenes)

    # Preserve unrelated media but register all source images in the bin.
    known = {item.path for item in project.media}
    for path in image_paths:
        if path not in known:
            project.media.append(
                MediaItem(
                    path=path,
                    kind="image",
                    role="detail",
                    start=0.0,
                    duration=4.0,
                    score=0.8,
                    motion="none",
                    keep_audio=False,
                    source_gain=0.0,
                )
            )
            known.add(path)

    project.timeline = []
    for index, (scene, duration) in enumerate(zip(scenes, durations)):
        role = scene.role
        if index == 0:
            role = "visual_hook"
        elif index == len(scenes) - 1:
            role = "ending"
        project.timeline.append(
            MediaItem(
                path=image_paths[index % len(image_paths)],
                kind="image",
                role=role,
                start=0.0,
                duration=duration,
                score=1.0 - index / max(100, len(scenes) * 10),
                motion="none",
                keep_audio=False,
                source_gain=0.0,
            )
        )

    project.texts = []
    hook_end = min(3.0, project.target_seconds)
    first = scenes[0]
    context = first.badge or "TIN TỨC"
    project.texts.extend(
        [
            TextItem(0.0, hook_end, context.upper(), "context", 0.5, 0.20, 60, 600, "#F4F1E9"),
            TextItem(0.5, hook_end, "ĐIỂM CHÍNH", "main", 0.5, 0.27, 102, 700, "#F4F1E9"),
            TextItem(1.0, hook_end, _hook_keyword(project.title), "keyword", 0.5, 0.36, 138, 800, "#FFC928"),
        ]
    )

    cursor = 0.0
    for index, (scene, duration) in enumerate(zip(scenes, durations)):
        start = cursor + 0.18
        end = cursor + duration - 0.18
        if index == 0:
            start = max(start, hook_end + 0.05)
        if end - start >= 0.35:
            project.texts.append(
                TextItem(
                    start=start,
                    end=end,
                    text=scene.summary or scene.title,
                    role="caption",
                    x=0.5,
                    y=0.78,
                    size=72,
                    weight=700,
                    color="#F4F1E9",
                    align="center",
                )
            )
        cursor += duration

    project.dirty = True
    return project


def apply_news_content(
    project: ProjectState,
    text: str,
    *,
    images: Iterable[str] | None = None,
    voice_duration: float | None = None,
    minimum_scenes: int = 0,
) -> ProjectState:
    scenes = parse_news_content(text, minimum_scenes=minimum_scenes)
    return apply_news_scenes(
        project,
        scenes,
        images=images,
        total_seconds=voice_duration,
        source_mode="NEWS_TEXT",
        source_text=text,
    )


def resync_story_to_duration(project: ProjectState, total_seconds: float) -> ProjectState:
    if not project.story_scenes:
        return project
    scenes = [_normalize_scene(item, index + 1) for index, item in enumerate(project.story_scenes)]
    images = [item.path for item in project.media if item.kind == "image"]
    return apply_news_scenes(
        project,
        scenes,
        images=images,
        total_seconds=total_seconds,
        source_mode=project.source_mode or "NEWS_TEXT",
        source_text=project.source_text,
        source_url=project.source_url,
        title=project.title,
    )
