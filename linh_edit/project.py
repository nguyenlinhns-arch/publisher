from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

CURRENT_PROJECT_SCHEMA = 2

ProfileName = Literal[
    "TRAVEL_DOCUMENTARY",
    "TALKING_HEAD_EXPERT",
    "EXPLAINER_NEWS",
    "DIRECT_RECRUITMENT",
]


@dataclass(slots=True)
class MediaItem:
    path: str
    kind: str = "video"
    role: str = "detail"
    start: float = 0.0
    duration: float = 3.4
    score: float = 0.5
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    motion: str = "none"
    keep_audio: bool = False
    source_gain: float = 0.10


@dataclass(slots=True)
class TextItem:
    start: float
    end: float
    text: str
    role: str = "caption"
    x: float = 0.5
    y: float = 0.78
    size: int = 72
    weight: int = 700
    color: str = "#F4F1E9"
    align: str = "center"


@dataclass(slots=True)
class SfxItem:
    path: str
    start: float
    gain: float = 0.30


@dataclass(slots=True)
class ProjectState:
    schema_version: int = CURRENT_PROJECT_SCHEMA
    name: str = "Dự án mới"
    profile: ProfileName = "TRAVEL_DOCUMENTARY"
    target_seconds: float = 75.0
    title: str = ""
    media: list[MediaItem] = field(default_factory=list)
    timeline: list[MediaItem] = field(default_factory=list)
    texts: list[TextItem] = field(default_factory=list)
    sfx: list[SfxItem] = field(default_factory=list)
    voiceover: str = ""
    music: str = ""
    music_gain: float = 0.14
    output_dir: str = ""
    source_mode: str = ""
    source_text: str = ""
    source_url: str = ""
    transcript: str = ""
    story_scenes: list[dict[str, Any]] = field(default_factory=list)
    dirty: bool = False

    def save(self, path: Path) -> None:
        path = path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["dirty"] = False
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        temp = path.with_suffix(path.suffix + ".partial")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)

        sidecar_stem = path.name
        if sidecar_stem.endswith(".linhedit.json"):
            sidecar_stem = sidecar_stem[: -len(".linhedit.json")]
        else:
            sidecar_stem = path.stem
        if self.transcript.strip():
            transcript_path = path.with_name(sidecar_stem + "_transcript.txt")
            transcript_temp = transcript_path.with_suffix(
                transcript_path.suffix + ".partial"
            )
            transcript_temp.write_text(
                self.transcript.strip() + "\n",
                encoding="utf-8",
            )
            transcript_temp.replace(transcript_path)
        if self.source_text.strip():
            source_path = path.with_name(sidecar_stem + "_source.txt")
            source_temp = source_path.with_suffix(source_path.suffix + ".partial")
            source_temp.write_text(self.source_text, encoding="utf-8")
            source_temp.replace(source_path)

        self.dirty = False

    @classmethod
    def load(cls, path: Path) -> "ProjectState":
        # Windows PowerShell 5.1 and both legacy Linh video apps may emit
        # UTF-8 JSON with a BOM. utf-8-sig accepts both BOM and plain UTF-8.
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Project Linh Edit phải là JSON object.")

        version = int(payload.get("schema_version", 1) or 1)
        if version > CURRENT_PROJECT_SCHEMA:
            raise ValueError(
                f"Project schema {version} mới hơn Linh Edit hỗ trợ "
                f"({CURRENT_PROJECT_SCHEMA})."
            )
        payload["schema_version"] = CURRENT_PROJECT_SCHEMA

        media = [MediaItem(**item) for item in payload.pop("media", [])]
        timeline = [MediaItem(**item) for item in payload.pop("timeline", [])]
        texts = [TextItem(**item) for item in payload.pop("texts", [])]
        sfx = [SfxItem(**item) for item in payload.pop("sfx", [])]

        # Ignore stale same-generation keys from experimental builds while
        # refusing future schema versions above. This keeps old projects usable
        # without silently accepting a truly newer project format.
        allowed = {item.name for item in fields(cls)}
        payload = {key: value for key, value in payload.items() if key in allowed}
        payload["dirty"] = False
        return cls(media=media, timeline=timeline, texts=texts, sfx=sfx, **payload)
