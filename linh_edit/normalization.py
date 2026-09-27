from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .media import MediaInfo, probe


@dataclass(frozen=True, slots=True)
class NormalizationPlan:
    source: str
    duration: float
    width: int
    height: int
    fps: float
    r_fps: float
    is_vfr: bool
    rotation: int
    hdr: bool
    pixel_format: str
    color_transfer: str
    color_space: str
    color_primaries: str
    proxy_recommended: bool
    cfr_recommended_for_analysis: bool
    rotation_normalization_recommended: bool
    hdr_proxy_tonemap_recommended: bool
    final_source_policy: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_normalization_plan(path: Path) -> NormalizationPlan:
    info: MediaInfo = probe(path)
    hdr = info.color_transfer.lower() in {"smpte2084", "arib-std-b67"}
    long_edge = max(info.width, info.height)
    notes: list[str] = []

    proxy_recommended = long_edge >= 2160 or info.video_codec == "hevc"
    if proxy_recommended:
        notes.append("Dùng proxy local để review/phân tích; final vẫn render từ source gốc.")
    if info.is_vfr:
        notes.append("VFR: analysis proxy nên CFR; không ép transcode source gốc.")
    if info.rotation % 360:
        notes.append("Có rotation metadata; phải giữ orientation khi tạo proxy/reframe.")
    if hdr:
        notes.append("HDR/HLG/PQ: preview cần pipeline màu riêng để tránh nhạt/cháy.")
    if info.height < info.width:
        notes.append("Footage ngang: cần reframe 9:16 trước khi final.")

    return NormalizationPlan(
        source=str(info.path),
        duration=round(info.duration, 3),
        width=info.width,
        height=info.height,
        fps=round(info.fps, 4),
        r_fps=round(info.r_fps, 4),
        is_vfr=info.is_vfr,
        rotation=info.rotation,
        hdr=hdr,
        pixel_format=info.pixel_format,
        color_transfer=info.color_transfer,
        color_space=info.color_space,
        color_primaries=info.color_primaries,
        proxy_recommended=proxy_recommended,
        cfr_recommended_for_analysis=info.is_vfr,
        rotation_normalization_recommended=bool(info.rotation % 360),
        hdr_proxy_tonemap_recommended=hdr,
        final_source_policy="KEEP_ORIGINAL_FOR_FINAL_RENDER",
        notes=tuple(notes),
    )
