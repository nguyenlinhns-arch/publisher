import json

import linh_edit.legacy_import as legacy
from linh_edit.project import ProjectState


def test_import_legacy_news_resolves_scene_images(tmp_path, monkeypatch):
    assets = tmp_path / "assets" / "news"
    assets.mkdir(parents=True)
    image = assets / "s01.jpg"
    image.write_bytes(b"fake-image")
    payload = {
        "schema_version": 1,
        "project": {"slug": "tin_cu"},
        "scenes": [
            {
                "id": "s01",
                "type": "news",
                "badge": "TIN TỨC",
                "title": "Tin cũ",
                "voice_text": "Lời đọc của cảnh tin cũ.",
                "summary": "Ý chính của cảnh.",
                "image": "assets/news/s01.jpg",
            }
        ],
    }
    script = tmp_path / "script.json"
    script.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")

    project = legacy.import_legacy_script(script, ProjectState(target_seconds=20))

    assert project.source_mode == "LEGACY_NEWS"
    assert project.timeline[0].path == str(image.resolve())
    assert project.profile == "EXPLAINER_NEWS"
    assert "Lời đọc" in project.transcript


def test_import_legacy_editorial_uses_linh_background_when_no_images(tmp_path, monkeypatch):
    background = tmp_path / "nen.png"
    background.write_bytes(b"fake-background")
    monkeypatch.setattr(legacy, "resolve_asset", lambda _relative: background)
    payload = {
        "schema_version": 1,
        "project": {"slug": "editorial_cu"},
        "scenes": [
            {
                "id": "s01",
                "type": "hero",
                "badge": "GIẢI ĐÁP",
                "title": "Một câu hỏi",
                "voice_text": "Đây là phần lời đọc của hero cũ.",
                "subtitle": "Phần phụ đề cũ.",
                "chips": [],
            },
            {
                "id": "s02",
                "type": "card",
                "title": "Ý thứ hai",
                "voice_text": "Đây là phần lời đọc của card cũ.",
                "items": [],
            },
        ],
    }
    script = tmp_path / "script.json"
    script.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    project = legacy.import_legacy_script(script, ProjectState(target_seconds=25))

    assert project.source_mode == "LEGACY_EDITORIAL"
    assert len(project.timeline) == 2
    assert all(item.path == str(background.resolve()) for item in project.timeline)
