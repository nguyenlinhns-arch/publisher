from pathlib import Path

from PIL import Image

import linh_edit.source_review as source_review
from linh_edit.media import MediaAudit, MediaInfo
from linh_edit.project import ProjectState


def test_candidate_windows_cover_clip_without_exceeding_bounds():
    items = source_review.candidate_windows(
        30.0,
        count=6,
        segment_seconds=3.4,
    )

    assert len(items) == 6
    assert items[0].start >= 0
    assert items[-1].end <= 30.0
    assert all(item.status == "PENDING_VISUAL_REVIEW" for item in items)


def test_short_clip_becomes_one_candidate():
    items = source_review.candidate_windows(2.0, count=12, segment_seconds=3.4)

    assert len(items) == 1
    assert items[0].start == 0.0
    assert items[0].end == 2.0


def test_review_video_writes_contact_sheet_candidate_frames_and_manifest(tmp_path, monkeypatch):
    video = tmp_path / "travel.mp4"
    video.write_bytes(b"video")

    monkeypatch.setattr(
        source_review,
        "probe",
        lambda _path: MediaInfo(
            path=video,
            duration=12.0,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
        ),
    )
    monkeypatch.setattr(
        source_review,
        "audit_media_info",
        lambda _info: MediaAudit(
            path=video,
            score=0.9,
            reject=False,
            reasons=(),
            warnings=(),
        ),
    )

    def fake_sheet(_source, target, **_kwargs):
        target.parent.mkdir(parents=True, exist_ok=True)
        # 4 columns x 1 row using the standard tile geometry.
        Image.new("RGB", (1120, 496), "gray").save(target)
        return target

    monkeypatch.setattr(source_review, "extract_contact_sheet", fake_sheet)

    item = source_review.review_video(
        video,
        tmp_path / "review",
        tiles=4,
        columns=4,
    )

    assert Path(item.contact_sheet).is_file()
    assert len(item.candidates) == 4
    assert all(Path(candidate.frame).is_file() for candidate in item.candidates)
    assert (Path(item.contact_sheet).parent / "review.json").is_file()


def test_build_source_review_keeps_partial_success(tmp_path, monkeypatch):
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")

    def fake_review(path, output_dir, **kwargs):
        if path.name == "bad.mp4":
            raise RuntimeError("bad clip")
        return source_review.SourceReviewItem(
            source=str(path),
            contact_sheet=str(output_dir / "good.jpg"),
            duration=5.0,
            width=1080,
            height=1920,
            fps=30.0,
            audit_score=0.9,
            audit_reject=False,
            audit_reasons=(),
            audit_warnings=(),
            candidates=source_review.candidate_windows(5.0, count=2),
        )

    monkeypatch.setattr(source_review, "review_video", fake_review)

    manifest = source_review.build_source_review(
        [good, bad],
        tmp_path / "out",
        tiles=2,
    )

    text = manifest.read_text(encoding="utf-8")
    assert "good.mp4" in text
    assert "bad clip" in text


def _review_manifest(tmp_path: Path, video: Path) -> Path:
    manifest = tmp_path / "source_review_manifest.json"
    payload = {
        "schema": source_review.REVIEW_SCHEMA,
        "items": [
            {
                "source": str(video),
                "contact_sheet": str(tmp_path / "sheet.jpg"),
                "duration": 10.0,
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "audit_score": 0.9,
                "audit_reject": False,
                "audit_reasons": [],
                "audit_warnings": [],
                "candidates": [
                    {
                        "index": 1,
                        "center": 2.0,
                        "start": 0.3,
                        "end": 3.7,
                        "duration": 3.4,
                        "frame": str(tmp_path / "candidate_01.jpg"),
                        "brightness": 0.5,
                        "contrast": 0.6,
                        "edge_energy": 0.7,
                        "technical_score": 0.8,
                        "duplicate_of": None,
                        "warnings": [],
                        "decision": "PENDING",
                        "review_note": "",
                        "status": "PENDING_VISUAL_REVIEW",
                    }
                ],
            }
        ],
        "errors": [],
        "policy": {"promotion_requires": "KEEP"},
    }
    source_review._atomic_json_write(manifest, payload)
    return manifest


def test_mark_review_then_promote_candidate(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    manifest = _review_manifest(tmp_path, video)

    project_path = tmp_path / "demo.linhedit.json"
    ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=45.0,
        source_mode="DIRECT_MEDIA",
    ).save(project_path)

    source_review.mark_candidate_review(
        manifest,
        item_index=1,
        candidate_index=1,
        decision="KEEP",
        note="Khung ổn, hành động rõ.",
    )
    result = source_review.promote_review_candidate(
        manifest,
        project_path,
        item_index=1,
        candidate_index=1,
        role="human",
        to_timeline=True,
    )

    saved = ProjectState.load(project_path)
    assert result["status"] == "DONE"
    assert len(saved.media) == 1
    assert len(saved.timeline) == 1
    assert saved.timeline[0].start == 0.3
    assert saved.timeline[0].role == "human"


def test_promote_requires_keep_decision(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    manifest = _review_manifest(tmp_path, video)
    project_path = tmp_path / "demo.linhedit.json"
    ProjectState().save(project_path)

    try:
        source_review.promote_review_candidate(
            manifest,
            project_path,
            item_index=1,
            candidate_index=1,
        )
    except ValueError as exc:
        assert "KEEP" in str(exc)
    else:
        raise AssertionError("Promotion must require KEEP.")
