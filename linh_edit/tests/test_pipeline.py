from pathlib import Path

import linh_edit.pipeline as pipeline
from linh_edit.project import MediaItem, ProjectState


def test_pipeline_optimizes_without_render(tmp_path, monkeypatch):
    media = []
    for index, role in enumerate(
        [
            "visual_hook",
            "human",
            "work",
            "road_reset",
            "place",
            "detail",
            "life",
            "emotion",
            "ending",
        ]
    ):
        path = tmp_path / f"{index}.mp4"
        path.write_bytes(b"x")
        media.append(
            MediaItem(
                path=str(path),
                role=role,
                duration=5.0,
                score=1.0 - index / 100,
            )
        )

    project_path = tmp_path / "travel.linhedit.json"
    ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=45.0,
        media=media,
        transcript=(
            "Tôi bắt đầu trên con đường vào làng. "
            "Sau đó gặp người dân và làm việc. "
            "Cuối ngày là cảm giác bình dị."
        ),
    ).save(project_path)

    result = pipeline.run_optimized_pipeline(
        project_path,
        render=False,
    )

    saved = ProjectState.load(project_path)
    assert result["status"] == "OPTIMIZED"
    assert saved.timeline
    assert any(item.role == "road_reset" for item in saved.timeline)
    assert any(item.role == "caption" for item in saved.texts)
    assert Path(result["receipt"]).is_file()
