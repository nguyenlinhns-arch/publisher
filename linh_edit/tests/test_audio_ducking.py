import json
from pathlib import Path

from linh_edit.engine.plan_io import load_plan
from linh_edit.engine_adapter import project_to_plan
from linh_edit.project import MediaItem, ProjectState


def test_project_schema_v2_migrates_audio_defaults(tmp_path: Path):
    path = tmp_path / "old.linhedit.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "profile": "TALKING_HEAD_EXPERT",
                "target_seconds": 10.0,
                "media": [],
                "timeline": [],
                "texts": [],
                "sfx": [],
                "music_gain": 0.12,
            }
        ),
        encoding="utf-8",
    )

    project = ProjectState.load(path)

    assert project.schema_version == 3
    assert project.auto_duck_music is True
    assert project.voice_gain == 1.0
    assert project.caption_coverage_target == 0.65


def test_project_to_plan_carries_ducking_settings(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    project = ProjectState(
        profile="TALKING_HEAD_EXPERT",
        target_seconds=3.0,
        timeline=[
            MediaItem(
                path=str(clip),
                role="human",
                duration=3.0,
                keep_audio=True,
                source_gain=1.0,
            )
        ],
        voice_gain=1.1,
        music_gain=0.11,
        auto_duck_music=True,
        duck_threshold=0.03,
        duck_ratio=7.0,
        duck_attack_ms=30.0,
        duck_release_ms=500.0,
    )
    plan_path = tmp_path / "plan.json"

    project_to_plan(project, plan_path)
    plan = load_plan(plan_path)

    assert plan.audio.voice_gain == 1.1
    assert plan.audio.music_gain == 0.11
    assert plan.audio.auto_duck_music is True
    assert plan.audio.duck_threshold == 0.03
    assert plan.audio.duck_ratio == 7.0
    assert plan.audio.duck_attack_ms == 30.0
    assert plan.audio.duck_release_ms == 500.0
