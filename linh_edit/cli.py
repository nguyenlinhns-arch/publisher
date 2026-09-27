from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .article_ingest import apply_article, fetch_article
from .engine_adapter import render_project
from .legacy_import import import_legacy_script
from .media import probe_duration
from .news_ingest import apply_news_content
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
    "source_modes": [
        "DIRECT_MEDIA",
        "NEWS_TEXT",
        "ARTICLE_URL",
        "LEGACY_NEWS",
        "LEGACY_EDITORIAL",
    ],
    "automation_commands": [
        "render",
        "legacy-import",
        "news-import",
        "article-import",
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
    render.add_argument("--visual-master", action="store_true")

    legacy = sub.add_parser("legacy-import")
    legacy.add_argument("--script", type=Path, required=True)
    legacy.add_argument("--project", type=Path, required=True)

    news = sub.add_parser("news-import")
    news.add_argument("--source", type=Path, required=True)
    news.add_argument("--image", type=Path, action="append", required=True)
    news.add_argument("--voice", type=Path)
    news.add_argument("--project", type=Path, required=True)
    news.add_argument("--minimum-scenes", type=int, default=3)

    article = sub.add_parser("article-import")
    article.add_argument("--url", required=True)
    article.add_argument("--workspace", type=Path, required=True)
    article.add_argument("--voice", type=Path)
    article.add_argument("--project", type=Path, required=True)
    return parser


def _safe_print(value: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        try:
            print(value, file=stream)
        except Exception:
            pass


def _save_result(project: ProjectState, path: Path, source_mode: str) -> int:
    target = path.expanduser().resolve()
    project.save(target)
    _safe_print(
        json.dumps(
            {
                "status": "DONE",
                "project": str(target),
                "profile": project.profile,
                "source_mode": source_mode,
                "scenes": len(project.timeline),
                "duration": round(sum(item.duration for item in project.timeline), 3),
            },
            ensure_ascii=False,
        )
    )
    return 0


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
                include_audio=not bool(args.visual_master),
            )
            _safe_print(
                json.dumps({"status": "DONE", "output": str(result)}, ensure_ascii=False)
            )
            return 0

        if command == "legacy-import":
            project = import_legacy_script(
                args.script.expanduser().resolve(),
                ProjectState(),
            )
            return _save_result(project, args.project, project.source_mode)

        if command == "news-import":
            source = args.source.expanduser().resolve()
            text = source.read_text(encoding="utf-8-sig")
            images = [str(path.expanduser().resolve()) for path in args.image]
            voice_duration = None
            project = ProjectState(profile="EXPLAINER_NEWS")
            if args.voice:
                voice = args.voice.expanduser().resolve()
                voice_duration = probe_duration(voice)
                project.voiceover = str(voice)
            apply_news_content(
                project,
                text,
                images=images,
                voice_duration=voice_duration,
                minimum_scenes=max(1, args.minimum_scenes),
            )
            return _save_result(project, args.project, project.source_mode)

        if command == "article-import":
            workspace = args.workspace.expanduser().resolve()
            workspace.mkdir(parents=True, exist_ok=True)
            article = fetch_article(args.url, workspace)
            project = ProjectState(profile="EXPLAINER_NEWS")
            voice_duration = None
            if args.voice:
                voice = args.voice.expanduser().resolve()
                voice_duration = probe_duration(voice)
                project.voiceover = str(voice)
            apply_article(project, article, total_seconds=voice_duration)
            return _save_result(project, args.project, project.source_mode)
    except Exception as exc:
        _safe_print(f"ERROR: {exc}", error=True)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
