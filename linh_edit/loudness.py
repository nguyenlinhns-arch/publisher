from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .checkpoint import create_checkpoint
from .project import ProjectState
from .tools import resolve_tool

JSON_RE = re.compile(r"\{[\s\S]*?\}", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class LoudnessMeasurement:
    path: str
    integrated_lufs: float
    true_peak_dbfs: float
    lra: float
    threshold: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_float(payload: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def parse_loudnorm_json(stderr: str, path: Path) -> LoudnessMeasurement:
    candidates = []
    for match in JSON_RE.finditer(stderr):
        text = match.group(0)
        if '"input_i"' not in text:
            continue
        try:
            candidates.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    if not candidates:
        raise ValueError("Không đọc được thống kê loudness từ FFmpeg.")
    payload = candidates[-1]
    return LoudnessMeasurement(
        path=str(path),
        integrated_lufs=_parse_float(payload, "input_i", -70.0),
        true_peak_dbfs=_parse_float(payload, "input_tp", -99.0),
        lra=_parse_float(payload, "input_lra", 0.0),
        threshold=_parse_float(payload, "input_thresh", -70.0),
    )


def measure_loudness(path: Path) -> LoudnessMeasurement:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"Không tìm thấy audio: {path}")
    completed = subprocess.run(
        [
            resolve_tool("ffmpeg"),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "FFmpeg loudness analysis failed")[-3000:])
    return parse_loudnorm_json(completed.stderr, path)


def gain_for_target(
    measured_lufs: float,
    target_lufs: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if measured_lufs <= -69:
        return 1.0
    delta_db = float(target_lufs) - float(measured_lufs)
    linear = 10 ** (delta_db / 20.0)
    return round(max(minimum, min(maximum, linear)), 4)


def auto_balance_project(
    project: ProjectState,
    *,
    voice_target_lufs: float = -16.0,
    music_target_lufs: float = -30.0,
) -> dict[str, Any]:
    results: dict[str, Any] = {
        "status": "DONE",
        "voice": None,
        "music": None,
    }
    if project.voiceover:
        path = Path(project.voiceover).expanduser().resolve()
        if path.is_file():
            measurement = measure_loudness(path)
            project.voice_gain = gain_for_target(
                measurement.integrated_lufs,
                voice_target_lufs,
                minimum=0.25,
                maximum=4.0,
            )
            results["voice"] = {
                **measurement.to_dict(),
                "target_lufs": voice_target_lufs,
                "recommended_gain": project.voice_gain,
            }

    if project.music:
        path = Path(project.music).expanduser().resolve()
        if path.is_file():
            measurement = measure_loudness(path)
            project.music_gain = gain_for_target(
                measurement.integrated_lufs,
                music_target_lufs,
                minimum=0.02,
                maximum=1.0,
            )
            results["music"] = {
                **measurement.to_dict(),
                "target_lufs": music_target_lufs,
                "recommended_gain": project.music_gain,
            }

    project.auto_master_audio = True
    project.dirty = True
    return results


def auto_balance_project_file(project_path: Path) -> dict[str, Any]:
    project_path = project_path.expanduser().resolve()
    project = ProjectState.load(project_path)
    checkpoint = create_checkpoint(
        project,
        project_path,
        label="before-audio-auto-master",
    )
    result = auto_balance_project(project)
    project.save(project_path)
    result["project"] = str(project_path)
    result["checkpoint"] = str(checkpoint)
    result["revision"] = project.revision
    return result
