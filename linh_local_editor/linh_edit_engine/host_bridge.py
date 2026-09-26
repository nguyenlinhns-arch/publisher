from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .plan_io import load_plan
from .renderer import render_plan


class HostBridge:
    """Thin integration surface for an existing desktop editor.

    The host keeps ownership of UI, manual timeline editing and project state.
    Linh Edit Engine only receives an explicit edit plan and returns artifacts.
    """

    bridge_version = "1.0"

    def capabilities(self) -> dict[str, Any]:
        return {
            "bridge_version": self.bridge_version,
            "profiles": [
                "TRAVEL_DOCUMENTARY",
                "TALKING_HEAD_EXPERT",
                "EXPLAINER_NEWS",
                "DIRECT_RECRUITMENT",
            ],
            "render_local": True,
            "requires_cloud": False,
            "output": {"width": 1080, "height": 1920, "fps": 30},
            "project_state_owner": "host_app",
        }

    def render(self, plan_path: str | Path, output_path: str | Path) -> dict[str, Any]:
        plan = load_plan(Path(plan_path))
        output = render_plan(plan, Path(output_path))
        qa_path = output.with_suffix(".qa.json")
        return {
            "status": "DONE",
            "output": str(output),
            "qa": str(qa_path),
            "profile": plan.profile,
            "duration": plan.duration,
        }


def write_capabilities(path: Path) -> None:
    path.write_text(
        json.dumps(HostBridge().capabilities(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
