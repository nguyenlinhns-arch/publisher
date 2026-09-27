from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .project import ProjectState

CHECKPOINT_SCHEMA = "linh-edit.checkpoint.v1"


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return cleaned[:48] or "checkpoint"


def checkpoint_root(project_path: Path) -> Path:
    project_path = project_path.expanduser().resolve()
    name = project_path.name
    if name.endswith(".linhedit.json"):
        name = name[: -len(".linhedit.json")]
    else:
        name = project_path.stem
    root = project_path.parent / ".linhedit_checkpoints" / _safe_label(name)
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_checkpoint(
    project: ProjectState,
    project_path: Path,
    *,
    label: str,
    keep: int = 24,
) -> Path:
    project_path = project_path.expanduser().resolve()
    root = checkpoint_root(project_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = root / f"{stamp}_{_safe_label(label)}.checkpoint.json"
    payload = {
        "schema": CHECKPOINT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "project_path": str(project_path),
        "project": asdict(project),
    }
    payload["project"]["dirty"] = False
    temp = target.with_suffix(target.suffix + ".partial")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(target)

    files = sorted(
        root.glob("*.checkpoint.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for stale in files[max(1, keep):]:
        try:
            stale.unlink()
        except OSError:
            pass
    return target


def list_checkpoints(project_path: Path) -> list[Path]:
    root = checkpoint_root(project_path)
    return sorted(
        root.glob("*.checkpoint.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def load_checkpoint(path: Path) -> ProjectState:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("schema") != CHECKPOINT_SCHEMA:
        raise ValueError("Checkpoint Linh Edit không hợp lệ.")
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise ValueError("Checkpoint thiếu project payload.")

    temp = path.with_name(path.name + ".project.partial.json")
    try:
        temp.write_text(
            json.dumps(project_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return ProjectState.load(temp)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def restore_checkpoint(checkpoint: Path, project_path: Path) -> ProjectState:
    project_path = project_path.expanduser().resolve()
    current = ProjectState.load(project_path)
    create_checkpoint(
        current,
        project_path,
        label="before-restore",
    )
    restored = load_checkpoint(checkpoint)
    # Restore content on top of the latest revision instead of rewinding the
    # revision counter. This keeps optimistic concurrency monotonic.
    restored.revision = current.revision
    restored.save(project_path)
    return restored
