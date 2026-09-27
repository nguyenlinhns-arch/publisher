from pathlib import Path

import linh_edit.source_review as source_review
from linh_edit.media import MediaAudit, MediaInfo


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


def test_review_video_writes_contact_sheet_and_manifest(tmp_path, monkeypatch):
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
        target.write_bytes(b"sheet")
        return target

    monkeypatch.setattr(source_review, "extract_contact_sheet", fake_sheet)

    item = source_review.review_video(video, tmp_path / "review", tiles=4)

    assert Path(item.contact_sheet).is_file()
    assert len(item.candidates) == 4
    assert (Path(item.contact_sheet).parent / "review.json").is_file()


def test_build_source_review_keeps_partial_success(tmp_path, monkeypatch):
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")

    original = source_review.review_video

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
