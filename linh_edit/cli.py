from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .engine_adapter import render_project
from .project import ProjectState
from .tools import resolve_tool


CAPABILITIES = {
    "app": APP_NAME,
    "version": __version__,
    "render": "local",
    "cloud_required": False,
    "profiles": [
        "TRAVEL_DOCUMENTARY",
        "TALKING_HEAD_EXPERT",
        "EXPLAINER_NEWS",
        "DIRECT_RECRUITMENT",
    ],
    "output_default": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_codec": "h264",
        "audio_codec": "aac",
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="LinhEdit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui")
    sub.add_parser("capabilities")
    sub.add_parser("doctor")

    render = sub.add_parser("render")
    render.add_argument("--project", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--preview", action="store_true")
    return parser


def _safe_print(value: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        try:
            print(value, file=stream)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "gui"

    if command == "gui":
        from .ui import main as gui_main
        return gui_main()

    try:
        if command == "capabilities":
            _safe_print(json.dumps(CAPABILITIES, ensure_ascii=False, indent=2))
            return 0

        if command == "doctor":
            payload = {
                **CAPABILITIES,
                "ffmpeg": resolve_tool("ffmpeg"),
                "ffprobe": resolve_tool("ffprobe"),
                "status": "READY",
            }
            _safe_print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if command == "render":
            project = ProjectState.load(args.project.expanduser().resolve())
            result = render_project(
                project,
                args.output.expanduser().resolve(),
                preview=bool(args.preview),
            )
            _safe_print(
                json.dumps({"status": "DONE", "output": str(result)}, ensure_ascii=False)
            )
            return 0
    except Exception as exc:
        _safe_print(f"ERROR: {exc}", error=True)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
