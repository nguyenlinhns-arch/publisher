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
    kind: Literal["video", "image"] = "video"
    role: str = "detail"
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    motion: Literal["none", "slow_zoom"] = "none"
    mute_source_audio: bool = True
    source_gain: float = 0.10
    hdr_to_sdr: bool = False

    def validate(self) -> None:
        if self.kind not in {"video", "image"}:
            raise ValueError("clip.kind must be video or image")
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
    voice_gain: float = 1.0
    auto_duck_music: bool = True
    duck_threshold: float = 0.025
    duck_ratio: float = 8.0
    duck_attack_ms: float = 25.0
    duck_release_ms: float = 450.0
    auto_master_audio: bool = True
    master_lufs: float = -14.0
    master_true_peak: float = -1.5
    master_lra: float = 11.0
    source_ambience_gain: float = 0.10
    ending_music_only_seconds: float = 6.0

    def validate(self) -> None:
        if not 0 <= self.music_gain <= 4:
            raise ValueError("audio.music_gain must be between 0 and 4")
        if not 0 <= self.voice_gain <= 4:
            raise ValueError("audio.voice_gain must be between 0 and 4")
        if not 0.0001 <= self.duck_threshold <= 1:
            raise ValueError("audio.duck_threshold must be between 0.0001 and 1")
        if not 1 <= self.duck_ratio <= 20:
            raise ValueError("audio.duck_ratio must be between 1 and 20")
        if not 1 <= self.duck_attack_ms <= 2000:
            raise ValueError("audio.duck_attack_ms out of range")
        if not 1 <= self.duck_release_ms <= 5000:
            raise ValueError("audio.duck_release_ms out of range")
        if not -24 <= self.master_lufs <= -8:
            raise ValueError("audio.master_lufs out of range")
        if not -6 <= self.master_true_peak <= -0.1:
            raise ValueError("audio.master_true_peak out of range")
        if not 1 <= self.master_lra <= 20:
            raise ValueError("audio.master_lra out of range")


@dataclass(frozen=True, slots=True)
class ExportSpec:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "192k"
    include_audio: bool = True

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
        self.audio.validate()
        self.export.validate()

    @property
    def duration(self) -> float:
        return sum(item.duration for item in self.clips)
