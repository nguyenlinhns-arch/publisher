import json

import pytest

from linh_edit.checkpoint import create_checkpoint, list_checkpoints, restore_checkpoint
from linh_edit.patches import apply_patch
from linh_edit.project import MediaItem, ProjectConflictError, ProjectState
from linh_edit.validation import validate_project


def _project(tmp_path):
    first = tmp_path / "one.mp4"
    second = tmp_path / "two.mp4"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=6.0,
        title="Original",
        source_mode="DIRECT_MEDIA",
        media=[
            MediaItem(path=str(first), role="human", duration=3.0, score=0.9),
            MediaItem(path=str(second), role="road_reset", duration=3.0, score=0.8),
        ],
        timeline=[
            MediaItem(path=str(first), role="human", duration=3.0, score=0.9),
            MediaItem(path=str(second), role="road_reset", duration=3.0, score=0.8),
        ],
    )
    return project


def test_project_load_migrates_old_schema_and_ignores_stale_key(tmp_path):
    path = tmp_path / "old.linhedit.json"
    path.write_text(
        json.dumps(
            {
                "name": "Old",
                "profile": "TRAVEL_DOCUMENTARY",
                "target_seconds": 45.0,
                "title": "",
                "media": [],
                "timeline": [],
                "texts": [],
                "sfx": [],
                "legacy_experiment": "ignore-me",
            }
        ),
        encoding="utf-8",
    )

    project = ProjectState.load(path)

    assert project.schema_version == 6
    assert project.name == "Old"


def test_project_load_refuses_future_schema(tmp_path):
    path = tmp_path / "future.linhedit.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "media": [],
                "timeline": [],
                "texts": [],
                "sfx": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mới hơn"):
        ProjectState.load(path)


def test_validation_flags_missing_media_and_travel_story_issues(tmp_path):
    project = ProjectState(
        profile="TRAVEL_DOCUMENTARY",
        target_seconds=45.0,
        media=[MediaItem(path=str(tmp_path / "missing.mp4"), role="work", duration=30)],
        timeline=[MediaItem(path=str(tmp_path / "missing.mp4"), role="work", duration=30)],
    )

    report = validate_project(project)

    assert not report.passed
    assert any(item.code == "MISSING_MEDIA" for item in report.errors)
    assert any(item.code == "TRAVEL_NO_ROAD_RESET" for item in report.warnings)
    assert any(item.code == "WORK_DOMINATES_TRAVEL" for item in report.warnings)


def test_patch_is_atomic_and_supports_timeline_and_hook(tmp_path):
    project = _project(tmp_path)
    payload = {
        "schema": "linh-edit.patch.v1",
        "operations": [
            {"op": "set_project", "values": {"title": "Patched"}},
            {"op": "move_timeline", "from": 1, "to": 0},
            {
                "op": "set_hook",
                "context": "GIA LAI",
                "main": "KHÔNG CHỈ CÓ",
                "keyword": "CÀ PHÊ",
            },
        ],
    }

    patched = apply_patch(project, payload)

    assert project.title == "Original"
    assert patched.title == "Patched"
    assert patched.timeline[0].role == "road_reset"
    assert [item.role for item in patched.texts] == ["context", "main", "keyword"]


def test_patch_rejects_invalid_operation_without_mutating_source(tmp_path):
    project = _project(tmp_path)
    payload = {
        "schema": "linh-edit.patch.v1",
        "operations": [
            {"op": "set_project", "values": {"title": "Should not stick"}},
            {"op": "remove_timeline", "index": 999},
        ],
    }

    with pytest.raises(ValueError):
        apply_patch(project, payload)

    assert project.title == "Original"
    assert len(project.timeline) == 2


def test_checkpoint_create_list_and_restore(tmp_path):
    project_path = tmp_path / "demo.linhedit.json"
    project = _project(tmp_path)
    project.save(project_path)

    checkpoint = create_checkpoint(project, project_path, label="before-edit")
    project.title = "Changed"
    project.save(project_path)

    restored = restore_checkpoint(checkpoint, project_path)

    assert restored.title == "Original"
    assert ProjectState.load(project_path).title == "Original"
    assert list_checkpoints(project_path)


def test_project_revision_blocks_stale_cross_process_save(tmp_path):
    path = tmp_path / "shared.linhedit.json"
    original = ProjectState(title="A")
    original.save(path)

    first = ProjectState.load(path)
    second = ProjectState.load(path)

    first.title = "First"
    first.save(path)

    second.title = "Second"
    with pytest.raises(ProjectConflictError):
        second.save(path)

    saved = ProjectState.load(path)
    assert saved.title == "First"
    assert saved.revision == first.revision


def test_project_revision_increments_monotonically(tmp_path):
    path = tmp_path / "revision.linhedit.json"
    project = ProjectState()

    project.save(path)
    first = project.revision
    project.title = "Updated"
    project.save(path)

    assert first == 1
    assert project.revision == 2
    assert ProjectState.disk_revision(path) == 2
