from __future__ import annotations

import json
from pathlib import Path

from .models import AudioSpec, ClipSpec, EditPlan, ExportSpec, SfxSpec, TextSpec


def _path(value: str | None, base: Path) -> Path | None:
    if not value:
        return None
    item = Path(value)
    return item if item.is_absolute() else (base / item).resolve()


def load_plan(path: Path) -> EditPlan:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent

    clips = tuple(
        ClipSpec(
            source=_path(item["source"], base),  # type: ignore[arg-type]
            start=float(item["start"]),
            duration=float(item["duration"]),
            role=str(item.get("role", "detail")),
            x=float(item.get("x", 0.5)),
            y=float(item.get("y", 0.5)),
            scale=float(item.get("scale", 1.0)),
            mute_source_audio=bool(item.get("mute_source_audio", True)),
            source_gain=float(item.get("source_gain", 0.10)),
        )
        for item in payload["clips"]
    )
    texts = tuple(
        TextSpec(
            start=float(item["start"]),
            end=float(item["end"]),
            text=str(item["text"]),
            role=str(item.get("role", "caption")),  # type: ignore[arg-type]
            x=float(item.get("x", 0.5)),
            y=float(item.get("y", 0.78)),
            size=int(item.get("size", 72)),
            weight=int(item.get("weight", 700)),
            color=str(item.get("color", "#F4F1E9")),
            align=str(item.get("align", "center")),  # type: ignore[arg-type]
        )
        for item in payload.get("texts", [])
    )
    audio_payload = payload.get("audio", {})
    sfx = tuple(
        SfxSpec(
            path=_path(item["path"], base),  # type: ignore[arg-type]
            start=float(item["start"]),
            gain=float(item.get("gain", 0.30)),
        )
        for item in audio_payload.get("sfx", [])
    )
    audio = AudioSpec(
        voiceover=_path(audio_payload.get("voiceover"), base),
        music=_path(audio_payload.get("music"), base),
        sfx=sfx,
        music_gain=float(audio_payload.get("music_gain", 0.14)),
        source_ambience_gain=float(audio_payload.get("source_ambience_gain", 0.10)),
        ending_music_only_seconds=float(audio_payload.get("ending_music_only_seconds", 6.0)),
    )
    export_payload = payload.get("export", {})
    export = ExportSpec(
        width=int(export_payload.get("width", 1080)),
        height=int(export_payload.get("height", 1920)),
        fps=int(export_payload.get("fps", 30)),
        crf=int(export_payload.get("crf", 18)),
        preset=str(export_payload.get("preset", "medium")),
        audio_bitrate=str(export_payload.get("audio_bitrate", "192k")),
    )
    plan = EditPlan(
        profile=str(payload["profile"]),  # type: ignore[arg-type]
        clips=clips,
        texts=texts,
        audio=audio,
        export=export,
        title=str(payload.get("title", "")),
    )
    plan.validate()
    return plan
