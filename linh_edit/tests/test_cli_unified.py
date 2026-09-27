import json

from linh_edit import cli


def test_capabilities_exposes_unified_sources():
    assert cli.CAPABILITIES["version"] == "1.1.0"
    assert "ARTICLE_URL" in cli.CAPABILITIES["source_modes"]
    assert "LEGACY_EDITORIAL" in cli.CAPABILITIES["source_modes"]
    assert "legacy-import" in cli.CAPABILITIES["automation_commands"]


def test_legacy_import_cli_saves_project(tmp_path):
    image_dir = tmp_path / "assets" / "news"
    image_dir.mkdir(parents=True)
    image = image_dir / "s01.jpg"
    image.write_bytes(b"image")
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": {"slug": "old_news"},
                "scenes": [
                    {
                        "id": "s01",
                        "type": "news",
                        "title": "Tin cũ",
                        "voice_text": "Lời đọc của bản tin cũ.",
                        "summary": "Ý chính.",
                        "image": "assets/news/s01.jpg",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    target = tmp_path / "migrated.linhedit.json"

    code = cli.main(
        [
            "legacy-import",
            "--script",
            str(script),
            "--project",
            str(target),
        ]
    )

    assert code == 0
    assert target.is_file()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source_mode"] == "LEGACY_NEWS"
    assert payload["profile"] == "EXPLAINER_NEWS"
