from pathlib import Path

import linh_edit.engine_adapter as adapter
from linh_edit.engine.plan_io import load_plan
from linh_edit.media import MediaInfo
from linh_edit.project import MediaItem, ProjectState


def test_project_to_plan_marks_hdr_video_for_sdr_tonemap(tmp_path, monkeypatch):
    clip = tmp_path / "hdr.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(
        adapter,
        "probe",
        lambda _path: MediaInfo(
            path=clip,
            duration=4.0,
            width=2160,
            height=3840,
            fps=30.0,
            has_audio=True,
            video_codec="hevc",
            audio_codec="aac",
            color_transfer="smpte2084",
            color_space="bt2020nc",
            color_primaries="bt2020",
        ),
    )
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=4.0,
        auto_hdr_to_sdr=True,
        timeline=[
            MediaItem(
                path=str(clip),
                role="place",
                duration=4.0,
            )
        ],
    )
    plan_path = tmp_path / "plan.json"

    adapter.project_to_plan(project, plan_path)
    plan = load_plan(plan_path)

    assert plan.clips[0].hdr_to_sdr is True


def test_project_to_plan_can_disable_hdr_tonemap(tmp_path, monkeypatch):
    clip = tmp_path / "hdr.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(
        adapter,
        "probe",
        lambda _path: MediaInfo(
            path=clip,
            duration=4.0,
            width=2160,
            height=3840,
            fps=30.0,
            has_audio=True,
            video_codec="hevc",
            audio_codec="aac",
            color_transfer="smpte2084",
        ),
    )
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        auto_hdr_to_sdr=False,
        timeline=[MediaItem(path=str(clip), duration=4.0)],
    )
    plan_path = tmp_path / "plan.json"

    adapter.project_to_plan(project, plan_path)
    plan = load_plan(plan_path)

    assert plan.clips[0].hdr_to_sdr is False
