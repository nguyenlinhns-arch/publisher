import json
from pathlib import Path

from linh_edit import cli
from linh_edit.media import MediaAudit, MediaInfo, audit_media_info
from linh_edit.project import MediaItem, ProjectState


def test_media_audit_rewards_vertical_1080p_30fps(tmp_path):
    path = tmp_path / "vertical.mp4"
    info = MediaInfo(
        path=path,
        duration=6.0,
        width=1080,
        height=1920,
        fps=30.0,
        has_audio=True,
        video_codec="h264",
        audio_codec="aac",
    )

    audit = audit_media_info(info)

    assert not audit.reject
    assert audit.score >= 0.80
    assert audit.needs_visual_review


def test_media_audit_rejects_sub_480p_source(tmp_path):
    path = tmp_path / "tiny.mp4"
    info = MediaInfo(
        path=path,
        duration=5.0,
        width=320,
        height=568,
        fps=30.0,
        has_audio=False,
        video_codec="h264",
        audio_codec=None,
    )

    audit = audit_media_info(info)

    assert audit.reject
    assert "resolution_below_480p" in audit.reasons


def test_media_audit_cli_reports_filtering(tmp_path, monkeypatch, capsys):
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"

    def fake_audit(path: Path):
        reject = path.name == "bad.mp4"
        return MediaAudit(
            path=path,
            score=0.9 if not reject else 0.2,
            reject=reject,
            reasons=("resolution_below_480p",) if reject else (),
            warnings=(),
        )

    monkeypatch.setattr(cli, "audit_video", fake_audit)

    code = cli.main(
        [
            "media-audit",
            "--media",
            str(good),
            "--media",
            str(bad),
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FILTERED"
    assert payload["rejected"] == 1


def test_project_patch_cli_creates_checkpoint_and_applies_patch(tmp_path, capsys):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"media")
    project_path = tmp_path / "demo.linhedit.json"
    project = ProjectState(
        profile="TALKING_HEAD_EXPERT",
        target_seconds=3.0,
        title="Before",
        media=[MediaItem(path=str(media), role="human", duration=3.0)],
        timeline=[
            MediaItem(
                path=str(media),
                role="human",
                duration=3.0,
                keep_audio=True,
                source_gain=1.0,
            )
        ],
    )
    project.save(project_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "schema": "linh-edit.patch.v1",
                "operations": [
                    {"op": "set_project", "values": {"title": "After"}},
                    {
                        "op": "set_hook",
                        "context": "TEST",
                        "main": "PATCH",
                        "keyword": "OK",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    code = cli.main(
        [
            "project-patch",
            "--project",
            str(project_path),
            "--patch",
            str(patch_path),
        ]
    )

    assert code == 0
    saved = ProjectState.load(project_path)
    assert saved.title == "After"
    output = json.loads(capsys.readouterr().out)
    assert Path(output["checkpoint"]).is_file()


def test_project_validate_cli_fails_for_missing_media(tmp_path, capsys):
    project_path = tmp_path / "broken.linhedit.json"
    project = ProjectState(
        profile="TALKING_HEAD_EXPERT",
        target_seconds=3.0,
        media=[MediaItem(path=str(tmp_path / "missing.mp4"), duration=3.0)],
        timeline=[MediaItem(path=str(tmp_path / "missing.mp4"), duration=3.0)],
    )
    project.save(project_path)

    code = cli.main(["project-validate", "--project", str(project_path)])

    assert code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "FAIL"
