from __future__ import annotations

import json
from dataclasses import asdict
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1] / "linh_local_editor"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from linh_edit_engine.plan_io import load_plan  # noqa: E402
from linh_edit_engine.renderer import render_plan  # noqa: E402

from .project import ProjectState


def _timeline_duration(project: ProjectState) -> float:
    return sum(x.duration for x in project.timeline)


def project_to_plan(project: ProjectState, plan_path: Path, *, preview: bool = False) -> Path:
    width, height = ((540, 960) if preview else (1080, 1920))
    crf = 25 if preview else 18
    preset = "veryfast" if preview else "medium"

    clips = []
    for item in project.timeline:
        clips.append(
            {
                "source": item.path,
                "start": item.start,
                "duration": item.duration,
                "role": item.role,
                "x": item.x,
                "y": item.y,
                "scale": item.scale,
                "mute_source_audio": not item.keep_audio,
                "source_gain": item.source_gain,
            }
        )

    payload = {
        "profile": project.profile,
        "title": project.title,
        "clips": clips,
        "texts": [asdict(x) for x in project.texts],
        "audio": {
            "voiceover": project.voiceover or None,
            "music": project.music or None,
            "music_gain": project.music_gain,
            "source_ambience_gain": 0.10,
            "ending_music_only_seconds": 6.0,
        },
        "export": {
            "width": width,
            "height": height,
            "fps": 30,
            "crf": crf,
            "preset": preset,
            "audio_bitrate": "128k" if preview else "192k",
        },
    }
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return plan_path


def render_project(project: ProjectState, output: Path, *, preview: bool = False) -> Path:
    plan_path = output.with_suffix(".plan.json")
    project_to_plan(project, plan_path, preview=preview)
    plan = load_plan(plan_path)
    return render_plan(plan, output)
