from pathlib import Path

from PIL import Image

import linh_edit.source_review as source_review
from linh_edit.media import MediaAudit, MediaInfo
from linh_edit.project import ProjectState
from linh_edit.visual_metrics import FrameMetrics


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
    proxy_path = tmp_path / "proxy.mp4"
    proxy_path.write_bytes(b"proxy")

    monkeypatch.setattr(
        source_review,
        "probe",
        lambda _path: MediaInfo(
            path=video,
            duration=12.0,
            width=2160,
            height=3840,
            fps=30.0,
            has_audio=True,
            video_codec="hevc",
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
    monkeypatch.setattr(
        source_review,
        "ensure_proxy",
        lambda _path: type(
            "Proxy",
            (),
            {"proxy": str(proxy_path), "reused": True},
        )(),
    )
    monkeypatch.setattr(
        source_review,
        "detect_shots",
        lambda _path: (
            source_review.ShotSpan(1, 0.0, 3.0, 3.0),
            source_review.ShotSpan(2, 3.0, 6.0, 3.0),
            source_review.ShotSpan(3, 6.0, 9.0, 3.0),
            source_review.ShotSpan(4, 9.0, 12.0, 3.0),
        ),
    )

    def fake_frames(_source, timestamps, output_dir, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        result = []
        for index, _timestamp in enumerate(timestamps, start=1):
            path = output_dir / f"candidate_{index:02d}.jpg"
            Image.new("RGB", (270, 480), (80 + index * 10, 100, 120)).save(path)
            result.append(path)
        return tuple(result)

    monkeypatch.setattr(source_review, "extract_candidate_frames", fake_frames)

    item = source_review.review_video(
        video,
        tmp_path / "review",
        tiles=4,
        columns=4,
    )

    assert Path(item.contact_sheet).is_file()
    assert len(item.candidates) == 4
    assert item.selection_mode == "SHOT_BOUNDARY"
    assert item.proxy_reused is True
    assert item.shot_count == 4
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


def test_global_duplicate_annotation_marks_cross_source_match():
    items = [
        {
            "candidates": [
                {"fingerprint": "0000000000000000", "global_duplicate_of": ""}
            ]
        },
        {
            "candidates": [
                {"fingerprint": "0000000000000000", "global_duplicate_of": ""}
            ]
        },
    ]

    source_review._annotate_global_duplicates(items)

    assert items[0]["candidates"][0]["global_duplicate_of"] == ""
    assert items[1]["candidates"][0]["global_duplicate_of"] == "1:1"


def test_enriched_candidates_receive_technical_rank(tmp_path, monkeypatch):
    frames = []
    for index in range(3):
        path = tmp_path / f"frame-{index}.jpg"
        Image.new("RGB", (270, 480), (80 + index * 40, 100, 120)).save(path)
        frames.append(path)

    scores = [0.25, 0.90, 0.55]

    def fake_metrics(path):
        index = int(path.stem.split("-")[-1])
        return FrameMetrics(
            brightness=0.5,
            contrast=0.5,
            edge_energy=0.5,
            technical_score=scores[index],
            dhash=f"{index + 1:016x}",
            warnings=(),
        )

    monkeypatch.setattr(source_review, "analyze_frame", fake_metrics)
    base = source_review.candidate_windows(12.0, count=3, segment_seconds=3.4)

    enriched = source_review._enrich_candidates(base, tuple(frames))

    assert [item.technical_rank for item in enriched] == [3, 1, 2]
    assert enriched[1].fingerprint


def test_mark_review_persists_selected_role(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    manifest = _review_manifest(tmp_path, video)

    source_review.mark_candidate_review(
        manifest,
        item_index=1,
        candidate_index=1,
        decision="KEEP",
        role="human",
        note="Giữ cảnh người.",
    )

    payload = source_review.load_review_manifest(manifest)
    candidate = payload["items"][0]["candidates"][0]
    assert candidate["decision"] == "KEEP"
    assert candidate["review_role"] == "human"


def test_apply_kept_candidates_builds_reviewed_only_rough_cut(tmp_path):
    keep = tmp_path / "keep.mp4"
    reject = tmp_path / "reject.mp4"
    keep.write_bytes(b"keep")
    reject.write_bytes(b"reject")

    manifest = tmp_path / "source_review_manifest.json"
    source_review._atomic_json_write(
        manifest,
        {
            "schema": source_review.REVIEW_SCHEMA,
            "items": [
                {
                    "source": str(keep),
                    "audit_score": 0.9,
                    "audit_reject": False,
                    "candidates": [
                        {
                            "index": 1,
                            "start": 1.0,
                            "duration": 4.0,
                            "technical_score": 0.8,
                            "decision": "KEEP",
                            "review_role": "human",
                        }
                    ],
                },
                {
                    "source": str(reject),
                    "audit_score": 0.9,
                    "audit_reject": False,
                    "candidates": [
                        {
                            "index": 1,
                            "start": 0.0,
                            "duration": 3.0,
                            "technical_score": 0.8,
                            "decision": "REJECT",
                            "review_role": "detail",
                        }
                    ],
                },
            ],
            "errors": [],
        },
    )
    project_path = tmp_path / "travel.linhedit.json"
    ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=45.0,
        source_mode="DIRECT_MEDIA",
    ).save(project_path)

    result = source_review.apply_kept_candidates(
        manifest,
        project_path,
        build_timeline=True,
    )

    saved = ProjectState.load(project_path)
    assert result["keep_candidates"] == 1
    assert len(saved.timeline) == 1
    assert saved.timeline[0].path == str(keep.resolve())
    assert saved.timeline[0].role == "human"


def test_candidates_from_shots_preserve_shot_bounds():
    spans = (
        source_review.ShotSpan(1, 0.0, 2.0, 2.0),
        source_review.ShotSpan(2, 2.0, 7.0, 5.0),
        source_review.ShotSpan(3, 7.0, 11.0, 4.0),
    )

    candidates = source_review.candidates_from_shots(
        spans,
        count=3,
        segment_seconds=3.4,
    )

    assert len(candidates) == 3
    assert candidates[0].start >= 0.0
    assert candidates[0].end <= 2.0
    assert candidates[1].start >= 2.0
    assert candidates[1].end <= 7.0
    assert candidates[2].start >= 7.0
    assert candidates[2].end <= 11.0


def test_review_cache_reuses_analysis_when_parameters_match(tmp_path):
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (270, 480), "gray").save(frame)
    item = source_review.SourceReviewItem(
        source=str(tmp_path / "clip.mp4"),
        contact_sheet=str(tmp_path / "sheet.jpg"),
        duration=6.0,
        width=1080,
        height=1920,
        fps=30.0,
        audit_score=0.9,
        audit_reject=False,
        audit_reasons=(),
        audit_warnings=(),
        candidates=(
            source_review.CandidateWindow(
                index=1,
                center=2.0,
                start=0.3,
                end=3.7,
                duration=3.4,
                frame=str(frame),
                technical_score=0.8,
            ),
        ),
    )
    manifest = tmp_path / "review.json"
    source_review._atomic_json_write(
        manifest,
        {
            "schema": source_review.REVIEW_SCHEMA,
            "engine_version": source_review.REVIEW_ENGINE_VERSION,
            "parameters": {
                "tiles": 12,
                "columns": 4,
                "candidate_seconds": 3.4,
            },
            **source_review.asdict(item),
        },
    )

    cached = source_review._cached_review_item(
        manifest,
        tiles=12,
        columns=4,
        candidate_seconds=3.4,
    )

    assert cached is not None
    assert cached.candidates[0].technical_score == 0.8


def test_preserved_decisions_survive_review_rebuild():
    existing = {
        "items": [
            {
                "source": "C:/video/clip.mp4",
                "candidates": [
                    {
                        "start": 1.0,
                        "end": 4.4,
                        "decision": "KEEP",
                        "review_role": "human",
                        "review_note": "Cảnh tốt",
                        "status": "VISUAL_REVIEWED",
                    }
                ],
            }
        ]
    }

    preserved = source_review._preserved_decisions(existing)

    key = source_review._decision_key(
        "C:/video/clip.mp4",
        {"start": 1.0, "end": 4.4},
    )
    assert preserved[key]["decision"] == "KEEP"
    assert preserved[key]["review_role"] == "human"
