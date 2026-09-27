from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .engine.plan_io import load_plan
from .engine.renderer import render_plan
from .final_qa import write_editorial_qa
from .media import probe

from .project import ProjectState
from .validation import validate_project


def _timeline_duration(project: ProjectState) -> float:
    return sum(x.duration for x in project.timeline)


def project_to_plan(
    project: ProjectState,
    plan_path: Path,
    *,
    preview: bool = False,
    include_audio: bool = True,
) -> Path:
    width, height = ((540, 960) if preview else (1080, 1920))
    crf = 25 if preview else 18
    preset = "veryfast" if preview else "medium"

    clips = []
    media_probe_cache: dict[str, object] = {}
    for item in project.timeline:
        hdr_to_sdr = False
        if project.auto_hdr_to_sdr and item.kind == "video":
            try:
                info = media_probe_cache.get(item.path)
                if info is None:
                    info = probe(Path(item.path))
                    media_probe_cache[item.path] = info
                hdr_to_sdr = str(getattr(info, "color_transfer", "")).lower() in {
                    "smpte2084",
                    "arib-std-b67",
                }
            except Exception:
                hdr_to_sdr = False
        clips.append(
            {
                "source": item.path,
                "kind": item.kind,
                "start": item.start,
                "duration": item.duration,
                "role": item.role,
                "x": item.x,
                "y": item.y,
                "scale": item.scale,
                "motion": item.motion,
                "mute_source_audio": not item.keep_audio,
                "source_gain": item.source_gain,
                "hdr_to_sdr": hdr_to_sdr,
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
            "sfx": [asdict(x) for x in project.sfx],
            "music_gain": project.music_gain,
            "voice_gain": project.voice_gain,
            "auto_duck_music": project.auto_duck_music,
            "duck_threshold": project.duck_threshold,
            "duck_ratio": project.duck_ratio,
            "duck_attack_ms": project.duck_attack_ms,
            "duck_release_ms": project.duck_release_ms,
            "auto_master_audio": project.auto_master_audio,
            "master_lufs": project.master_lufs,
            "master_true_peak": project.master_true_peak,
            "master_lra": project.master_lra,
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
            "include_audio": bool(include_audio),
        },
    }
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return plan_path


def render_project(
    project: ProjectState,
    output: Path,
    *,
    preview: bool = False,
    include_audio: bool = True,
) -> Path:
    output = output.expanduser().resolve()
    report = validate_project(project, deep=False)
    preflight_path = output.with_suffix(".preflight.json")
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    preflight_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not report.passed:
        summary = "; ".join(item.message for item in report.errors[:8])
        raise RuntimeError("Project preflight failed: " + summary)

    plan_path = output.with_suffix(".plan.json")
    project_to_plan(
        project,
        plan_path,
        preview=preview,
        include_audio=include_audio,
    )
    plan = load_plan(plan_path)
    result = render_plan(plan, output)
    try:
        write_editorial_qa(
            result,
            project,
            preview=preview,
        )
    except Exception as exc:
        editorial_error = output.with_suffix(".editorial_qa_error.txt")
        editorial_error.write_text(
            f"{type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
    return result
