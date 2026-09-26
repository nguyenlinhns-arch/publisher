from __future__ import annotations

from pathlib import Path

from .plan_io import load_plan
from .qa import QAResult, verify_output
from .renderer import render_plan


def render_edit_plan(plan_path: str | Path, output_path: str | Path) -> Path:
    plan = load_plan(Path(plan_path))
    return render_plan(plan, Path(output_path))


def verify_render(output_path: str | Path) -> QAResult:
    return verify_output(Path(output_path))
