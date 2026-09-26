import json

from linh_edit.news_ingest import (
    allocate_scene_seconds,
    apply_news_content,
    parse_news_content,
    resync_story_to_duration,
)
from linh_edit.project import ProjectState


def test_news_parser_accepts_legacy_scene_json():
    payload = {
        "scenes": [
            {
                "title": "Tin một",
                "voice_text": "Đây là đoạn lời đọc thứ nhất.",
                "summary": "Ý chính thứ nhất.",
                "badge": "TIN NGÀNH THAN",
            },
            {
                "title": "Tin hai",
                "voice_text": "Đây là đoạn lời đọc thứ hai.",
                "summary": "Ý chính thứ hai.",
            },
        ]
    }
    scenes = parse_news_content(json.dumps(payload, ensure_ascii=False))
    assert len(scenes) == 2
    assert scenes[0].badge == "TIN NGÀNH THAN"
    assert scenes[1].title == "Tin hai"


def test_plain_news_text_becomes_multiple_scenes():
    text = " ".join(
        [
            "Đây là câu mở đầu của bản tin với thông tin quan trọng.",
            "Nội dung tiếp theo giải thích bối cảnh và những gì đã diễn ra.",
            "Một chi tiết khác giúp người xem hiểu rõ sự việc hơn.",
            "Phần sau mở rộng câu chuyện bằng một dữ kiện mới.",
            "Cuối cùng là ý kết thúc ngắn gọn và dễ nhớ.",
        ]
    )
    scenes = parse_news_content(text, minimum_scenes=3)
    assert len(scenes) >= 3
    assert all(scene.voice_text for scene in scenes)


def test_scene_duration_allocation_preserves_exact_total():
    scenes = parse_news_content(
        json.dumps(
            {
                "scenes": [
                    {"voice_text": "Một đoạn ngắn."},
                    {"voice_text": "Đây là một đoạn dài hơn với nhiều từ hơn để kiểm tra tỷ lệ."},
                    {"voice_text": "Đoạn cuối."},
                ]
            },
            ensure_ascii=False,
        )
    )
    durations = allocate_scene_seconds(scenes, 31.25)
    assert round(sum(durations), 3) == 31.25
    assert durations[1] > durations[0]


def test_apply_news_builds_story_timeline_hook_and_transcript(tmp_path):
    image = tmp_path / "news.jpg"
    project = ProjectState(profile="EXPLAINER_NEWS", target_seconds=45)
    content = json.dumps(
        {
            "scenes": [
                {"title": "Cảnh một", "voice_text": "Lời đọc cảnh một.", "summary": "Ý một."},
                {"title": "Cảnh hai", "voice_text": "Lời đọc cảnh hai.", "summary": "Ý hai."},
            ]
        },
        ensure_ascii=False,
    )

    apply_news_content(project, content, images=[str(image)], voice_duration=20.0)

    assert project.source_mode == "NEWS_TEXT"
    assert project.target_seconds == 20.0
    assert len(project.timeline) == 2
    assert project.timeline[0].role == "visual_hook"
    assert project.timeline[-1].role == "ending"
    assert len([item for item in project.texts if item.role in {"context", "main", "keyword"}]) == 3
    assert "Lời đọc cảnh một." in project.transcript

    resync_story_to_duration(project, 24.0)
    assert project.target_seconds == 24.0
    assert round(sum(item.duration for item in project.timeline), 3) == 24.0
