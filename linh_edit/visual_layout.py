from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from .subject_detection import SubjectDetection, detect_subject


@dataclass(frozen=True, slots=True)
class LayoutSuggestion:
    subject_x: float
    subject_y: float
    subject_kind: str
    subject_confidence: float
    reframe_x: float
    reframe_y: float
    negative_space: str
    hook_layout: str
    hook_style: str
    hook_x: float
    hook_y: float
    hook_align: str
    local_brightness: float
    local_texture: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _edge_centroid(gray: Image.Image) -> tuple[float, float, float]:
    small = gray.resize((128, 128), Image.Resampling.LANCZOS)
    edges = small.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    mean = float(stat.mean[0])
    std = float(stat.stddev[0])
    threshold = min(255.0, mean + std * 0.65)

    pixels = list(edges.getdata())
    total = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    active = 0
    for y in range(5, 123):
        row = y * 128
        for x in range(5, 123):
            value = float(pixels[row + x])
            if value < threshold:
                continue
            weight = value - threshold + 1.0
            total += weight
            weighted_x += x * weight
            weighted_y += y * weight
            active += 1
    if total <= 0:
        return 0.5, 0.5, 0.0
    confidence = _clamp(active / (118 * 118 * 0.22), 0.0, 1.0)
    return (
        _clamp(weighted_x / total / 127.0, 0.0, 1.0),
        _clamp(weighted_y / total / 127.0, 0.0, 1.0),
        confidence,
    )


def _region_stats(gray: Image.Image, box: tuple[float, float, float, float]) -> tuple[float, float]:
    width, height = gray.size
    left = max(0, round(box[0] * width))
    top = max(0, round(box[1] * height))
    right = min(width, round(box[2] * width))
    bottom = min(height, round(box[3] * height))
    if right <= left or bottom <= top:
        return 0.5, 1.0
    region = gray.crop((left, top, right, bottom))
    brightness = float(ImageStat.Stat(region).mean[0]) / 255.0
    edges = region.filter(ImageFilter.FIND_EDGES)
    texture = float(ImageStat.Stat(edges).mean[0]) / 255.0
    return brightness, texture


def _reframe_axis(
    subject: float,
    source_extent: float,
    crop_extent: float,
) -> float:
    available = source_extent - crop_extent
    if available <= 1e-6:
        return 0.5
    subject_px = subject * source_extent
    crop_start = _clamp(subject_px - crop_extent / 2, 0.0, available)
    return _clamp(crop_start / available, 0.0, 1.0)


def analyze_layout(
    frame: Path,
    *,
    target_aspect: float = 9 / 16,
    subject_override: SubjectDetection | None = None,
) -> LayoutSuggestion:
    frame = frame.expanduser().resolve()
    with Image.open(frame) as opened:
        image = opened.convert("RGB")
        gray = image.convert("L")
        width, height = image.size
        subject_x, subject_y, confidence = _edge_centroid(gray)
        subject_kind = "saliency"
        subject_confidence = confidence
        detected = subject_override or detect_subject(frame)
        if detected is not None and (
            subject_override is not None
            or detected.confidence >= max(0.45, confidence)
        ):
            subject_x = detected.x
            subject_y = detected.y
            subject_kind = detected.kind
            subject_confidence = detected.confidence

        regions = {
            "LEFT": (0.04, 0.12, 0.46, 0.62),
            "CENTER": (0.25, 0.10, 0.75, 0.55),
            "TOP": (0.12, 0.04, 0.88, 0.34),
        }
        stats = {
            name: _region_stats(gray, box)
            for name, box in regions.items()
        }

    # Penalize both detail and extreme luminance: clean negative space should
    # be visually quiet and readable, not just black/white.
    def clutter(name: str) -> float:
        brightness, texture = stats[name]
        luminance_penalty = max(0.0, abs(brightness - 0.48) - 0.20) * 0.18
        return texture + luminance_penalty

    negative = min(regions, key=clutter)
    if negative == "TOP":
        hook_layout = "UPPER-CENTER"
        hook_x, hook_y, hook_align = 0.5, 0.18, "center"
    elif negative == "LEFT" and subject_x >= 0.48:
        hook_layout = "CENTER-LEFT"
        hook_x, hook_y, hook_align = 0.12, 0.27, "left"
    else:
        hook_layout = "CENTER"
        hook_x, hook_y, hook_align = 0.5, 0.25, "center"

    brightness, texture = stats[negative]
    hook_style = (
        "HIGH_CONTRAST"
        if brightness >= 0.68 or texture >= 0.16
        else "CLEAN"
    )

    source_aspect = width / max(1, height)
    reframe_x, reframe_y = 0.5, 0.5
    if source_aspect > target_aspect:
        crop_width = height * target_aspect
        reframe_x = _reframe_axis(subject_x, width, crop_width)
    elif source_aspect < target_aspect:
        crop_height = width / target_aspect
        reframe_y = _reframe_axis(subject_y, height, crop_height)

    return LayoutSuggestion(
        subject_x=round(subject_x, 4),
        subject_y=round(subject_y, 4),
        subject_kind=subject_kind,
        subject_confidence=round(subject_confidence, 4),
        reframe_x=round(reframe_x, 4),
        reframe_y=round(reframe_y, 4),
        negative_space=negative,
        hook_layout=hook_layout,
        hook_style=hook_style,
        hook_x=hook_x,
        hook_y=hook_y,
        hook_align=hook_align,
        local_brightness=round(brightness, 4),
        local_texture=round(texture, 4),
        confidence=round(confidence, 4),
    )
