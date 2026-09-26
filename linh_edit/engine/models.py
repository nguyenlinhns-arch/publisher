from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ProfileName = Literal[
    "TRAVEL_DOCUMENTARY",
    "TALKING_HEAD_EXPERT",
    "EXPLAINER_NEWS",
    "DIRECT_RECRUITMENT",
]


@dataclass(frozen=True, slots=True)
class ClipSpec:
    source: Path
    start: float
    duration: float
    role: str = "detail"
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    mute_source_audio: bool = True
    source_gain: float = 0.10

    def validate(self) -> None:
        if self.start < 0:
            raise ValueError("clip.start must be >= 0")
        if self.duration <= 0:
            raise ValueError("clip.duration must be > 0")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("clip x/y must be normalized to 0..1")
        if self.scale <= 0:
            raise ValueError("clip.scale must be > 0")
        if self.source_gain < 0 or self.source_gain > 4:
            raise ValueError("clip.source_gain must be between 0 and 4")


@dataclass(frozen=True, slots=True)
class TextSpec:
    start: float
    end: float
    text: str
    role: Literal["context", "main", "keyword", "caption", "location"] = "caption"
    x: float = 0.5
    y: float = 0.78
    size: int = 72
    weight: int = 700
    color: str = "#F4F1E9"
    align: Literal["left", "center", "right"] = "center"

    def validate(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("invalid text time range")
        if not self.text.strip():
            raise ValueError("text cannot be empty")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("text x/y must be normalized to 0..1")


@dataclass(frozen=True, slots=True)
class SfxSpec:
    path: Path
    start: float
    gain: float = 0.30

    def validate(self) -> None:
        if self.start < 0:
            raise ValueError("sfx.start must be >= 0")
        if self.gain < 0 or self.gain > 4:
            raise ValueError("sfx.gain must be between 0 and 4")


@dataclass(frozen=True, slots=True)
class AudioSpec:
    voiceover: Path | None = None
    music: Path | None = None
    sfx: tuple[SfxSpec, ...] = ()
    music_gain: float = 0.14
    source_ambience_gain: float = 0.10
    ending_music_only_seconds: float = 6.0


@dataclass(frozen=True, slots=True)
class ExportSpec:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("invalid export geometry/fps")
        if self.width >= self.height:
            raise ValueError("Linh vertical profiles require portrait output")


@dataclass(frozen=True, slots=True)
class EditPlan:
    profile: ProfileName
    clips: tuple[ClipSpec, ...]
    texts: tuple[TextSpec, ...] = ()
    audio: AudioSpec = field(default_factory=AudioSpec)
    export: ExportSpec = field(default_factory=ExportSpec)
    title: str = ""

    def validate(self) -> None:
        if not self.clips:
            raise ValueError("edit plan requires at least one clip")
        for clip in self.clips:
            clip.validate()
        for text in self.texts:
            text.validate()
        for sfx in self.audio.sfx:
            sfx.validate()
        self.export.validate()

    @property
    def duration(self) -> float:
        return sum(item.duration for item in self.clips)
