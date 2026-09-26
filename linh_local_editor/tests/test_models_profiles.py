from pathlib import Path

from linh_edit_engine.compiler import FootageCandidate, compile_travel_plan
from linh_edit_engine.models import ClipSpec, EditPlan
from linh_edit_engine.profiles import get_profile


def test_travel_profile_defaults():
    profile = get_profile("TRAVEL_DOCUMENTARY")
    assert profile.target_min_seconds == 45
    assert profile.target_max_seconds == 90
    assert profile.hard_cut_first
    assert profile.road_reset
    assert profile.hook_layers == 3


def test_plan_duration():
    plan = EditPlan(
        profile="TRAVEL_DOCUMENTARY",
        clips=(
            ClipSpec(Path("a.mp4"), 0, 3.0),
            ClipSpec(Path("b.mp4"), 2, 4.0),
        ),
    )
    assert plan.duration == 7.0


def test_travel_compiler_filters_and_orders():
    roles = [
        "visual_hook", "human", "work", "road_reset", "place", "detail",
        "human", "road_reset", "life", "emotion", "ending",
    ]
    items = [
        FootageCandidate(
            source=Path(f"{i}.mp4"),
            start=0.0,
            available_duration=6.0,
            role=role,
            score=1.0 - i / 100,
        )
        for i, role in enumerate(roles)
    ]
    plan = compile_travel_plan(items, target_seconds=45)
    assert plan.profile == "TRAVEL_DOCUMENTARY"
    assert plan.clips[0].role == "visual_hook"
    assert any(item.role == "road_reset" for item in plan.clips)
    assert plan.duration >= 30
