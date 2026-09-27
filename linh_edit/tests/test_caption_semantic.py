from pathlib import Path

import linh_edit.caption_planner as captions
import linh_edit.semantic_match as semantic
from linh_edit.project import MediaItem, ProjectState


def test_selective_caption_plan_skips_hook_and_limits_coverage():
    transcript = (
        "Buổi sáng tôi rời thị trấn và bắt đầu đi qua con đường đèo. "
        "Sau đó tôi gặp bà con trong một ngôi làng nhỏ. "
        "Buổi chiều là thời gian làm việc và trao đổi hồ sơ. "
        "Điều còn lại trong tôi là cảm giác rất bình dị."
    )

    blocks = captions.plan_selective_captions(
        transcript,
        30.0,
        hook_end=3.0,
        coverage_target=0.60,
    )

    assert blocks
    assert all(block.start >= 3.0 for block in blocks)
    assert any(block.desired_role for block in blocks)
    assert sum(block.duration for block in blocks) <= 30.0


def test_apply_selective_captions_preserves_hook_layers():
    project = ProjectState(
        transcript=(
            "Tôi đi trên con đường vào làng. "
            "Sau đó gặp người dân và dành thời gian cho công việc."
        ),
        target_seconds=20.0,
        timeline=[
            MediaItem(path="a.mp4", role="road_reset", duration=10.0),
            MediaItem(path="b.mp4", role="human", duration=10.0),
        ],
    )
    project.texts = []

    result = captions.apply_selective_captions(project, coverage_target=0.65)

    assert result["caption_blocks"] >= 1
    assert all(item.role == "caption" for item in project.texts)
    assert all(item.y == 0.78 for item in project.texts)


def test_text_shot_match_swaps_only_duration_compatible_local_slots():
    project = ProjectState(
        transcript=(
            "Tôi gặp người dân trong làng. "
            "Sau đó chúng tôi đi tiếp trên con đường dài."
        ),
        target_seconds=8.0,
        timeline=[
            MediaItem(path="road.mp4", role="road_reset", duration=4.0),
            MediaItem(path="human.mp4", role="human", duration=4.0),
        ],
    )

    result = semantic.apply_text_shot_matching(
        project,
        coverage_target=1.0,
        max_distance=2,
    )

    assert result["swap_count"] >= 1
    assert sum(item.duration for item in project.timeline) == 8.0
