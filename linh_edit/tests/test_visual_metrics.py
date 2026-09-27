from pathlib import Path

from PIL import Image

from linh_edit.visual_metrics import (
    analyze_frame,
    annotate_duplicate_groups,
    extract_contact_sheet_tiles,
    hamming_distance,
)


def test_visual_metrics_scores_clean_contrast_frame(tmp_path: Path):
    image = Image.new("RGB", (270, 480), "white")
    for x in range(0, 270, 20):
        for y in range(0, 480, 20):
            if (x // 20 + y // 20) % 2:
                for ix in range(x, min(x + 10, 270)):
                    for iy in range(y, min(y + 10, 480)):
                        image.putpixel((ix, iy), (0, 0, 0))
    path = tmp_path / "sharp.jpg"
    image.save(path)

    metrics = analyze_frame(path)

    assert metrics.technical_score > 0.25
    assert len(metrics.dhash) == 16


def test_dhash_distance_detects_identical_images(tmp_path: Path):
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    Image.new("RGB", (270, 480), (100, 120, 140)).save(first)
    Image.new("RGB", (270, 480), (100, 120, 140)).save(second)

    left = analyze_frame(first)
    right = analyze_frame(second)

    assert hamming_distance(left.dhash, right.dhash) == 0
    assert annotate_duplicate_groups((left, right)) == (None, 1)


def test_extract_contact_sheet_tiles_uses_ffmpeg_tile_geometry(tmp_path: Path):
    tile_w, tile_h, padding, margin = 270, 480, 8, 8
    columns, rows = 2, 2
    width = margin * 2 + columns * tile_w + (columns - 1) * padding
    height = margin * 2 + rows * tile_h + (rows - 1) * padding
    sheet = Image.new("RGB", (width, height), "gray")
    path = tmp_path / "sheet.jpg"
    sheet.save(path)

    outputs = extract_contact_sheet_tiles(
        path,
        tmp_path / "tiles",
        tiles=4,
        columns=2,
    )

    assert len(outputs) == 4
    assert all(item.is_file() for item in outputs)
