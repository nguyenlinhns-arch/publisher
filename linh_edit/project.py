from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

ProfileName = Literal[
    "TRAVEL_DOCUMENTARY",
    "TALKING_HEAD_EXPERT",
    "EXPLAINER_NEWS",
    "DIRECT_RECRUITMENT",
]


@dataclass(slots=True)
class MediaItem:
    path: str
    role: str = "detail"
    start: float = 0.0
    duration: float = 3.4
    score: float = 0.5
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
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
    dirty: bool = False

    def save(self, path: Path) -> None:
        payload = asdict(self)
        payload["dirty"] = False
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.dirty = False

    @classmethod
    def load(cls, path: Path) -> "ProjectState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        media = [MediaItem(**item) for item in payload.pop("media", [])]
        timeline = [MediaItem(**item) for item in payload.pop("timeline", [])]
        texts = [TextItem(**item) for item in payload.pop("texts", [])]
        sfx = [SfxItem(**item) for item in payload.pop("sfx", [])]
        payload["dirty"] = False
        return cls(media=media, timeline=timeline, texts=texts, sfx=sfx, **payload)
