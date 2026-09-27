from pathlib import Path

from PIL import Image, ImageDraw

from linh_edit.visual_layout import analyze_layout


def test_layout_detects_left_negative_space_and_reframe(tmp_path: Path):
    image = Image.new("RGB", (1280, 720), (130, 130, 130))
    draw = ImageDraw.Draw(image)
    # Put a high-detail subject on the right half.
    for x in range(760, 1180, 20):
        draw.line((x, 120, x, 650), fill=(245, 245, 245), width=6)
    path = tmp_path / "landscape.jpg"
    image.save(path)

    layout = analyze_layout(path)

    assert layout.subject_x > 0.5
    assert layout.reframe_x > 0.5
    assert layout.hook_layout in {"CENTER-LEFT", "UPPER-CENTER", "CENTER"}


def test_layout_exact_vertical_needs_no_reframe(tmp_path: Path):
    path = tmp_path / "vertical.jpg"
    Image.new("RGB", (1080, 1920), (80, 90, 100)).save(path)

    layout = analyze_layout(path)

    assert layout.reframe_x == 0.5
    assert layout.reframe_y == 0.5
