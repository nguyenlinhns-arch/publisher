from __future__ import annotations

import json
from pathlib import Path

from .planner import IMAGE_EXTENSIONS
from .project import MediaItem, ProjectState, SfxItem, TextItem


def _resolve(base: Path, value: str | None) -> str:
    if not value:
        return ""
    path = Path(value)
    return str(path if path.is_absolute() else (base / path).resolve())


def import_storyboard(path: Path, project: ProjectState) -> ProjectState:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent

    assets = payload.get("media") or payload.get("images") or []
    if isinstance(assets, str):
        assets = [assets]
    assets = [_resolve(base, str(x)) for x in assets]

    scenes = payload.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Storyboard cần mảng 'scenes' có ít nhất một cảnh.")
    if not assets and not any(scene.get("media") or scene.get("image") for scene in scenes):
        raise ValueError("Storyboard cần ít nhất một media/image.")

    project.profile = str(payload.get("profile") or "EXPLAINER_NEWS")  # type: ignore[assignment]
    project.title = str(payload.get("title") or project.title)
    project.voiceover = _resolve(base, payload.get("voiceover")) or project.voiceover
    project.music = _resolve(base, payload.get("music")) or project.music
    if "music_gain" in payload:
        project.music_gain = float(payload["music_gain"])

    project.timeline.clear()
    project.texts.clear()
    project.sfx.clear()

    transition_sfx = _resolve(base, payload.get("transition_sfx"))
    transition_gain = float(payload.get("transition_sfx_gain", 0.30))
    cursor = 0.0

    for index, scene in enumerate(scenes):
        explicit = scene.get("media") or scene.get("image")
        source = _resolve(base, explicit) if explicit else assets[index % len(assets)]
        source_path = Path(source)
        kind = "image" if source_path.suffix.lower() in IMAGE_EXTENSIONS else "video"
        duration = float(scene.get("duration", 4.0 if kind == "image" else 3.4))
        if duration <= 0:
            raise ValueError(f"Cảnh {index + 1} có duration không hợp lệ.")

        item = MediaItem(
            path=source,
            kind=kind,
            role=str(scene.get("role", "detail")),
            start=float(scene.get("start", 0.0)),
            duration=duration,
            score=float(scene.get("score", 0.5)),
            x=float(scene.get("x", 0.5)),
            y=float(scene.get("y", 0.5)),
            scale=float(scene.get("scale", 1.0)),
            motion=str(scene.get("motion", "slow_zoom" if kind == "image" else "none")),
            keep_audio=bool(scene.get("keep_audio", False)),
            source_gain=float(scene.get("source_gain", 0.10)),
        )
        project.timeline.append(item)

        text = str(scene.get("text") or "").strip()
        if text:
            project.texts.append(
                TextItem(
                    start=cursor + 0.15,
                    end=max(cursor + 0.25, cursor + duration - 0.15),
                    text=text,
                    role=str(scene.get("text_role", "caption")),
                    x=float(scene.get("text_x", 0.5)),
                    y=float(scene.get("text_y", 0.78)),
                    size=int(scene.get("text_size", 72)),
                    weight=int(scene.get("text_weight", 700)),
                    color=str(scene.get("text_color", "#F4F1E9")),
                    align=str(scene.get("text_align", "center")),
                )
            )
        if transition_sfx:
            project.sfx.append(
                SfxItem(
                    path=transition_sfx,
                    start=cursor,
                    gain=transition_gain,
                )
            )
        cursor += duration

    project.target_seconds = cursor
    project.dirty = True
    return project
