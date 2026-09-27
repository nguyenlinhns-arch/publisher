from pathlib import Path

from PIL import Image

import linh_edit.analysis_frames as frames


def test_compose_contact_sheet_labels_candidates(tmp_path: Path):
    sources = []
    for index in range(5):
        path = tmp_path / f"{index}.jpg"
        Image.new("RGB", (270, 480), (40 * index, 80, 120)).save(path)
        sources.append(path)

    target = tmp_path / "sheet.jpg"
    result = frames.compose_contact_sheet(tuple(sources), target, columns=4)

    assert result.is_file()
    with Image.open(result) as image:
        assert image.width > 4 * 270
        assert image.height > 480
