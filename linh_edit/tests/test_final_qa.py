from linh_edit.final_qa import project_edit_metrics
from linh_edit.project import MediaItem, ProjectState, TextItem


def test_project_edit_metrics_reports_travel_structure():
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=45.0,
        timeline=[
            MediaItem("a.mp4", role="visual_hook", duration=3.0),
            MediaItem("b.mp4", role="human", duration=4.5),
            MediaItem("c.mp4", role="work", duration=2.5),
            MediaItem("d.mp4", role="road_reset", duration=3.0),
            MediaItem("e.mp4", role="place", duration=3.4),
            MediaItem("f.mp4", role="emotion", duration=4.8),
            MediaItem("g.mp4", role="ending", duration=5.5),
        ],
        texts=[
            TextItem(0, 3, "GIA LAI", "context"),
            TextItem(0.5, 3, "KHÔNG CHỈ CÓ", "main"),
            TextItem(1, 3, "CÀ PHÊ", "keyword"),
        ],
    )

    metrics = project_edit_metrics(project)

    assert metrics["road_resets"] == 1
    assert metrics["work_ratio"] < 0.2
    assert metrics["hook_roles"] == ["context", "keyword", "main"]
    assert metrics["unique_sources"] == 7


def test_project_edit_metrics_warns_consecutive_duplicate_source():
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        timeline=[
            MediaItem("same.mp4", role="human", duration=4.0),
            MediaItem("same.mp4", role="detail", duration=3.0),
        ],
    )

    metrics = project_edit_metrics(project)

    assert "consecutive_same_source" in metrics["warnings"]
