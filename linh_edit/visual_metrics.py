from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

TILE_PADDING = 8
TILE_MARGIN = 8


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    brightness: float
    contrast: float
    edge_energy: float
    technical_score: float
    dhash: str
    warnings: tuple[str, ...]


def _crop_analysis_area(image: Image.Image) -> Image.Image:
    width, height = image.size
    inset_x = max(1, round(width * 0.05))
    inset_y = max(1, round(height * 0.05))
    if width <= inset_x * 2 or height <= inset_y * 2:
        return image
    return image.crop((inset_x, inset_y, width - inset_x, height - inset_y))


def _dhash(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    value = 0
    bit = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            left = pixels[offset + column]
            right = pixels[offset + column + 1]
            if left > right:
                value |= 1 << bit
            bit += 1
    return f"{value:016x}"


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def analyze_frame(path: Path) -> FrameMetrics:
    path = path.expanduser().resolve()
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        analysis = _crop_analysis_area(image)
        gray = analysis.convert("L")
        stat = ImageStat.Stat(gray)
        mean = float(stat.mean[0])
        stddev = float(stat.stddev[0])

        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        edge_variance = float(edge_stat.var[0])

        brightness = max(0.0, min(1.0, mean / 255.0))
        contrast = max(0.0, min(1.0, stddev / 64.0))
        edge_energy = max(0.0, min(1.0, edge_variance / 900.0))

        # Technical ranking only. It intentionally does not decide whether a
        # frame is aesthetically good or whether a face/action is cropped.
        brightness_score = 1.0
        if brightness < 0.18:
            brightness_score = max(0.0, brightness / 0.18)
        elif brightness > 0.88:
            brightness_score = max(0.0, (1.0 - brightness) / 0.12)

        technical_score = (
            0.50 * edge_energy
            + 0.30 * contrast
            + 0.20 * brightness_score
        )
        warnings: list[str] = []
        if brightness < 0.10:
            warnings.append("very_dark")
        elif brightness < 0.16:
            warnings.append("dark")
        if brightness > 0.94:
            warnings.append("very_bright")
        elif brightness > 0.90:
            warnings.append("bright")
        if contrast < 0.10:
            warnings.append("low_contrast")
        if edge_energy < 0.10:
            warnings.append("soft_or_low_detail")

        return FrameMetrics(
            brightness=round(brightness, 4),
            contrast=round(contrast, 4),
            edge_energy=round(edge_energy, 4),
            technical_score=round(max(0.0, min(1.0, technical_score)), 4),
            dhash=_dhash(analysis),
            warnings=tuple(warnings),
        )


def extract_contact_sheet_tiles(
    sheet: Path,
    output_dir: Path,
    *,
    tiles: int,
    columns: int,
    tile_width: int = 270,
    tile_height: int = 480,
    padding: int = TILE_PADDING,
    margin: int = TILE_MARGIN,
) -> tuple[Path, ...]:
    sheet = sheet.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tiles = max(1, int(tiles))
    columns = max(1, int(columns))

    result: list[Path] = []
    with Image.open(sheet) as opened:
        image = opened.convert("RGB")
        for index in range(tiles):
            row, column = divmod(index, columns)
            left = margin + column * (tile_width + padding)
            top = margin + row * (tile_height + padding)
            right = left + tile_width
            bottom = top + tile_height
            if right > image.width or bottom > image.height:
                break
            tile = image.crop((left, top, right, bottom))
            target = output_dir / f"candidate_{index + 1:02d}.jpg"
            tile.save(target, format="JPEG", quality=92, optimize=True)
            result.append(target.resolve())
    return tuple(result)


def annotate_duplicate_groups(metrics: tuple[FrameMetrics, ...], *, threshold: int = 4) -> tuple[int | None, ...]:
    duplicates: list[int | None] = []
    for index, item in enumerate(metrics):
        duplicate_of: int | None = None
        for previous_index, previous in enumerate(metrics[:index]):
            if hamming_distance(item.dhash, previous.dhash) <= threshold:
                duplicate_of = previous_index + 1
                break
        duplicates.append(duplicate_of)
    return tuple(duplicates)
