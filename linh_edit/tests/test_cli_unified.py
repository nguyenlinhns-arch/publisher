import json

from linh_edit import cli


def test_capabilities_exposes_unified_sources():
    assert cli.CAPABILITIES["version"] == "1.5.0"
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


def test_media_import_cli_builds_direct_media_project(tmp_path, monkeypatch):
    media = tmp_path / "talk.mp4"
    media.write_bytes(b"media")
    target = tmp_path / "direct.linhedit.json"

    monkeypatch.setattr(
        cli,
        "import_media",
        lambda paths: [
            cli.ProjectState.__dataclass_fields__ and __import__(
                "linh_edit.project", fromlist=["MediaItem"]
            ).MediaItem(
                path=str(paths[0]),
                kind="video",
                role="human",
                duration=10.0,
                score=1.0,
            )
        ],
    )

    code = cli.main(
        [
            "media-import",
            "--media",
            str(media),
            "--profile",
            "TALKING_HEAD_EXPERT",
            "--target-seconds",
            "10",
            "--project",
            str(target),
        ]
    )

    assert code == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source_mode"] == "DIRECT_MEDIA"
    assert payload["profile"] == "TALKING_HEAD_EXPERT"
    assert payload["timeline"][0]["keep_audio"] is True


def test_project_status_cli_reports_saved_project(tmp_path, capsys):
    target = tmp_path / "status.linhedit.json"
    project = cli.ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        source_mode="DIRECT_MEDIA",
        title="Status test",
    )
    project.save(target)

    code = cli.main(["project-status", "--project", str(target)])

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "READY"
    assert output["title"] == "Status test"
