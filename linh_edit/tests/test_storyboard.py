import json

from linh_edit.project import ProjectState
from linh_edit.storyboard import import_storyboard


def test_storyboard_reuses_single_image_and_builds_scene_text(tmp_path):
    payload = {
        "profile": "EXPLAINER_NEWS",
        "title": "Tin thử",
        "images": ["one.jpg"],
        "transition_sfx": "cut.mp3",
        "scenes": [
            {"duration": 2.0, "text": "Cảnh một"},
            {"duration": 3.0, "text": "Cảnh hai"},
            {"duration": 4.0, "text": "Cảnh ba"},
        ],
    }
    path = tmp_path / "story.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    project = import_storyboard(path, ProjectState())

    assert project.profile == "EXPLAINER_NEWS"
    assert len(project.timeline) == 3
    assert len(project.media) == 1
    assert all(item.kind == "image" for item in project.timeline)
    assert len(project.texts) == 3
    assert len(project.sfx) == 3
    assert project.target_seconds == 9.0


def test_storyboard_accepts_windows_utf8_bom(tmp_path):
    payload = {
        "profile": "EXPLAINER_NEWS",
        "title": "Tin Windows",
        "images": ["one.jpg"],
        "scenes": [{"duration": 2.0, "text": "BOM OK"}],
    }
    path = tmp_path / "story-bom.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")

    project = import_storyboard(path, ProjectState())

    assert project.title == "Tin Windows"
    assert len(project.timeline) == 1
    assert project.texts[0].text == "BOM OK"
