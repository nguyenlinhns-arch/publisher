from pathlib import Path

from PIL import Image

import linh_edit.subject_detection as subject
import linh_edit.visual_layout as layout


def test_track_subject_medians_multiple_detections(monkeypatch, tmp_path: Path):
    frames = []
    for index in range(3):
        path = tmp_path / f"{index}.jpg"
        Image.new("RGB", (100, 100), "gray").save(path)
        frames.append(path)

    values = {
        "0.jpg": subject.SubjectDetection("face", 0.7, 0.4, 0.2, 0.3, 0.9),
        "1.jpg": subject.SubjectDetection("face", 0.8, 0.5, 0.2, 0.3, 0.8),
        "2.jpg": subject.SubjectDetection("face", 0.9, 0.6, 0.2, 0.3, 0.85),
    }
    monkeypatch.setattr(subject, "detect_subject", lambda path: values[path.name])

    tracked = subject.track_subject(tuple(frames))

    assert tracked is not None
    assert tracked.kind == "face"
    assert tracked.x == 0.8
    assert tracked.y == 0.5


def test_visual_layout_prefers_detected_subject_over_edge_centroid(monkeypatch, tmp_path: Path):
    path = tmp_path / "frame.jpg"
    Image.new("RGB", (1280, 720), (120, 120, 120)).save(path)
    monkeypatch.setattr(
        layout,
        "detect_subject",
        lambda _path: subject.SubjectDetection(
            "face", 0.82, 0.45, 0.12, 0.20, 0.95
        ),
    )

    suggestion = layout.analyze_layout(path)

    assert suggestion.subject_kind == "face"
    assert suggestion.subject_x == 0.82
    assert suggestion.reframe_x > 0.5
    assert suggestion.subject_confidence == 0.95
