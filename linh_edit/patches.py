from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .project import MediaItem, ProjectState, SfxItem, TextItem
from .validation import validate_project

PATCH_SCHEMA = "linh-edit.patch.v1"

PROJECT_FIELDS = {
    "name",
    "profile",
    "target_seconds",
    "title",
    "voiceover",
    "music",
    "music_gain",
    "voice_gain",
    "auto_duck_music",
    "duck_threshold",
    "duck_ratio",
    "duck_attack_ms",
    "duck_release_ms",
    "caption_coverage_target",
    "output_dir",
    "source_mode",
    "source_text",
    "source_url",
    "transcript",
}
MEDIA_FIELDS = {
    "path",
    "kind",
    "role",
    "start",
    "duration",
    "score",
    "x",
    "y",
    "scale",
    "motion",
    "keep_audio",
    "source_gain",
}


def _index(items: list[Any], value: Any, label: str) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} phải là số nguyên.") from exc
    if not 0 <= index < len(items):
        raise ValueError(f"{label} ngoài phạm vi: {index}.")
    return index


def _set_known(target: Any, values: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("Field patch không được phép: " + ", ".join(sorted(unknown)))
    for key, value in values.items():
        setattr(target, key, value)


def _text_from_payload(payload: dict[str, Any]) -> TextItem:
    return TextItem(
        start=float(payload["start"]),
        end=float(payload["end"]),
        text=str(payload["text"]),
        role=str(payload.get("role", "caption")),
        x=float(payload.get("x", 0.5)),
        y=float(payload.get("y", 0.78)),
        size=int(payload.get("size", 72)),
        weight=int(payload.get("weight", 700)),
        color=str(payload.get("color", "#F4F1E9")),
        align=str(payload.get("align", "center")),
    )


def _sfx_from_payload(payload: dict[str, Any]) -> SfxItem:
    return SfxItem(
        path=str(payload["path"]),
        start=float(payload["start"]),
        gain=float(payload.get("gain", 0.30)),
    )


def _apply_one(project: ProjectState, op: dict[str, Any]) -> None:
    name = str(op.get("op") or "").strip()
    if not name:
        raise ValueError("Patch operation thiếu 'op'.")

    if name == "set_project":
        values = op.get("values")
        if not isinstance(values, dict):
            raise ValueError("set_project.values phải là object.")
        _set_known(project, values, PROJECT_FIELDS)
        return

    if name == "update_media":
        index = _index(project.media, op.get("index"), "media index")
        values = op.get("values")
        if not isinstance(values, dict):
            raise ValueError("update_media.values phải là object.")
        _set_known(project.media[index], values, MEDIA_FIELDS)
        return

    if name == "move_media":
        source = _index(project.media, op.get("from"), "media from")
        destination = _index(project.media, op.get("to"), "media to")
        item = project.media.pop(source)
        project.media.insert(destination, item)
        return

    if name == "update_timeline":
        index = _index(project.timeline, op.get("index"), "timeline index")
        values = op.get("values")
        if not isinstance(values, dict):
            raise ValueError("update_timeline.values phải là object.")
        _set_known(project.timeline[index], values, MEDIA_FIELDS)
        return

    if name == "move_timeline":
        source = _index(project.timeline, op.get("from"), "timeline from")
        destination = _index(project.timeline, op.get("to"), "timeline to")
        item = project.timeline.pop(source)
        project.timeline.insert(destination, item)
        return

    if name == "remove_timeline":
        index = _index(project.timeline, op.get("index"), "timeline index")
        project.timeline.pop(index)
        return

    if name == "duplicate_timeline":
        index = _index(project.timeline, op.get("index"), "timeline index")
        project.timeline.insert(index + 1, MediaItem(**asdict(project.timeline[index])))
        return

    if name == "add_timeline":
        payload = op.get("item")
        if not isinstance(payload, dict):
            raise ValueError("add_timeline.item phải là object.")
        item = MediaItem(**payload)
        at = op.get("at")
        if at is None:
            project.timeline.append(item)
        else:
            at_index = int(at)
            if not 0 <= at_index <= len(project.timeline):
                raise ValueError("add_timeline.at ngoài phạm vi.")
            project.timeline.insert(at_index, item)
        return

    if name == "set_hook":
        project.texts = [
            item
            for item in project.texts
            if item.role not in {"context", "main", "keyword"}
        ]
        end = float(op.get("end", 3.0))
        context = str(op.get("context") or "").strip()
        main = str(op.get("main") or "").strip()
        keyword = str(op.get("keyword") or "").strip()
        if context:
            project.texts.append(
                TextItem(0.0, end, context, "context", 0.5, 0.20, 60, 600, "#F4F1E9")
            )
        if main:
            project.texts.append(
                TextItem(0.5, end, main, "main", 0.5, 0.27, 102, 700, "#F4F1E9")
            )
        if keyword:
            project.texts.append(
                TextItem(1.0, end, keyword, "keyword", 0.5, 0.36, 150, 800, "#FFC928")
            )
        return

    if name == "add_text":
        payload = op.get("item")
        if not isinstance(payload, dict):
            raise ValueError("add_text.item phải là object.")
        project.texts.append(_text_from_payload(payload))
        return

    if name == "update_text":
        index = _index(project.texts, op.get("index"), "text index")
        values = op.get("values")
        if not isinstance(values, dict):
            raise ValueError("update_text.values phải là object.")
        allowed = {"start", "end", "text", "role", "x", "y", "size", "weight", "color", "align"}
        _set_known(project.texts[index], values, allowed)
        return

    if name == "remove_text":
        index = _index(project.texts, op.get("index"), "text index")
        project.texts.pop(index)
        return

    if name == "set_audio":
        values = op.get("values")
        if not isinstance(values, dict):
            raise ValueError("set_audio.values phải là object.")
        allowed = {
            "voiceover",
            "music",
            "music_gain",
            "voice_gain",
            "auto_duck_music",
            "duck_threshold",
            "duck_ratio",
            "duck_attack_ms",
            "duck_release_ms",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError("Audio field không được phép: " + ", ".join(sorted(unknown)))
        for key, value in values.items():
            setattr(project, key, value)
        return

    if name == "add_sfx":
        payload = op.get("item")
        if not isinstance(payload, dict):
            raise ValueError("add_sfx.item phải là object.")
        project.sfx.append(_sfx_from_payload(payload))
        return

    if name == "remove_sfx":
        index = _index(project.sfx, op.get("index"), "sfx index")
        project.sfx.pop(index)
        return

    if name == "clear_sfx":
        project.sfx.clear()
        return

    raise ValueError(f"Patch operation chưa hỗ trợ: {name}")


def apply_patch(project: ProjectState, payload: dict[str, Any]) -> ProjectState:
    if not isinstance(payload, dict) or payload.get("schema") != PATCH_SCHEMA:
        raise ValueError(f"Patch phải dùng schema {PATCH_SCHEMA}.")
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("Patch cần ít nhất một operation.")
    if len(operations) > 100:
        raise ValueError("Patch vượt quá 100 operations.")

    candidate = deepcopy(project)
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"Operation {index + 1} phải là object.")
        try:
            _apply_one(candidate, operation)
        except Exception as exc:
            raise ValueError(f"Operation {index + 1} lỗi: {exc}") from exc

    candidate.dirty = True
    report = validate_project(candidate, deep=False)
    if report.errors:
        summary = "; ".join(item.message for item in report.errors[:8])
        raise ValueError("Patch tạo project không hợp lệ: " + summary)
    return candidate


def load_patch(path: Path) -> dict[str, Any]:
    import json

    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Patch JSON phải là object.")
    return payload
