from pathlib import Path

from linh_edit.planner import build_rough_cut
from linh_edit.project import MediaItem, ProjectState


def test_travel_rough_cut_has_road_reset():
    project = ProjectState(profile="TRAVEL_DOCUMENTARY", target_seconds=45)
    roles = [
        "visual_hook", "human", "work", "road_reset", "place", "detail",
        "life", "road_reset", "human", "detail", "emotion", "ending",
    ]
    project.media = [
        MediaItem(path=f"{i}.mp4", role=role, duration=4.5, score=1.0 - i/100)
        for i, role in enumerate(roles)
    ]
    timeline = build_rough_cut(project)
    assert timeline
    assert timeline[0].role == "visual_hook"
    assert any(x.role == "road_reset" for x in timeline)


def test_talk_keeps_source_audio():
    project = ProjectState(profile="TALKING_HEAD_EXPERT", target_seconds=10)
    project.media = [MediaItem(path="talk.mp4", role="human", duration=10, score=1)]
    timeline = build_rough_cut(project)
    assert timeline[0].keep_audio
    assert timeline[0].source_gain == 1.0


def test_news_reuses_image_media_when_scenes_outnumber_assets():
    project = ProjectState(profile="EXPLAINER_NEWS", target_seconds=20)
    project.media = [
        MediaItem(
            path="news.jpg",
            kind="image",
            role="detail",
            duration=4.0,
            score=1.0,
            motion="slow_zoom",
        )
    ]
    timeline = build_rough_cut(project)
    assert len(timeline) == 5
    assert all(item.kind == "image" for item in timeline)
    assert sum(item.duration for item in timeline) == 20.0
