from pathlib import Path

import linh_edit.review_gate as review_gate
import linh_edit.speech_rhythm as rhythm
import linh_edit.story_optimizer as story
from linh_edit.project import MediaItem, ProjectState


def test_story_optimizer_caps_work_and_keeps_road_reset():
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=45.0,
    )
    roles = [
        "visual_hook", "human", "work", "work", "road_reset", "place",
        "detail", "life", "human", "detail", "emotion", "ending",
        "place", "detail", "life",
    ]
    project.media = [
        MediaItem(
            path=f"{index}.mp4",
            role=role,
            duration=5.0,
            score=1.0 - index / 100,
        )
        for index, role in enumerate(roles)
    ]

    result = story.optimize_story(project)

    assert result["scenes"] >= 8
    assert result["work_ratio"] <= 0.35 + 1e-6
    assert result["road_resets"] >= 1
    assert project.timeline[0].role == "visual_hook"


def test_parse_silence_and_talk_punch_split_preserves_duration(monkeypatch):
    project = ProjectState(
        profile="TALKING_HEAD_EXPERT",
        target_seconds=8.0,
        transcript="Câu thứ nhất. Câu thứ hai. Câu thứ ba.",
        timeline=[
            MediaItem(
                path="talk.mp4",
                role="human",
                start=2.0,
                duration=8.0,
                keep_audio=True,
                source_gain=1.0,
            )
        ],
    )
    monkeypatch.setattr(
        rhythm,
        "detect_silences",
        lambda _path: (
            rhythm.SilenceSpan(2.1, 2.5),
            rhythm.SilenceSpan(5.0, 5.4),
        ),
    )
    project.voiceover = "voice.wav"

    result = rhythm.apply_talk_rhythm(project, minimum_segment=1.0)

    assert result["status"] == "DONE"
    assert abs(sum(item.duration for item in project.timeline) - 8.0) < 0.01
    assert any(item.scale > 1.0 for item in project.timeline)
    assert project.timeline[0].start == 2.0


def test_review_gate_becomes_stale_after_content_edit(tmp_path: Path):
    path = tmp_path / "review.linhedit.json"
    project = ProjectState()
    project.save(path)

    review_gate.set_review_stage(path, stage="visual", value="PASS")
    review_gate.set_review_stage(path, stage="audio", value="PASS")
    review_gate.set_review_stage(path, stage="full", value="PASS")

    approved = ProjectState.load(path)
    assert approved.ready_to_publish()

    approved.title = "Changed"
    approved.dirty = True
    approved.save(path)

    changed = ProjectState.load(path)
    state = review_gate.review_status(changed)
    assert not state["review_current"]
    assert not state["ready_to_publish"]
