from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .article_ingest import apply_article, fetch_article
from .cache import cache_summary, prune_cache
from .caption_planner import (
    apply_selective_captions_to_file,
    project_caption_plan,
)
from .checkpoint import create_checkpoint, list_checkpoints, restore_checkpoint
from .engine_adapter import render_project
from .final_qa import analyze_render
from .legacy_import import import_legacy_script
from .loudness import auto_balance_project_file, measure_loudness
from .media import audit_video, probe_duration
from .proxy import ensure_proxy
from .news_ingest import apply_news_content
from .normalization import build_normalization_plan
from .patches import apply_patch, load_patch
from .pipeline import run_optimized_pipeline
from .planner import build_rough_cut, import_media
from .project import ProjectState
from .review_gate import reset_review, review_status, set_review_stage
from .semantic_match import (
    apply_text_shot_matching_to_file,
    build_text_shot_report,
)
from .shot_detection import detect_shots
from .speech_rhythm import apply_talk_rhythm_to_file
from .story_optimizer import optimize_story_to_file
from .source_review import (
    apply_candidate_hook_layout,
    apply_kept_candidates,
    build_source_review,
    mark_candidate_review,
    promote_review_candidate,
)
from .tools import resolve_tool
from .validation import validate_project


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
        "media-import",
        "project-status",
        "project-validate",
        "project-patch",
        "project-checkpoint",
        "checkpoint-list",
        "checkpoint-restore",
        "media-audit",
        "source-review",
        "review-mark",
        "review-promote",
        "review-build",
        "proxy-build",
        "shot-detect",
        "cache-status",
        "normalization-plan",
        "cache-prune",
        "hook-layout-apply",
        "caption-plan",
        "caption-apply",
        "text-shot-report",
        "text-shot-apply",
        "transcript-set",
        "story-optimize",
        "talk-rhythm-apply",
        "review-status",
        "review-set",
        "review-reset",
        "audio-analyze",
        "audio-auto-master",
        "qa-analyze",
        "optimize-all",
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

    media = sub.add_parser("media-import")
    media.add_argument("--media", type=Path, action="append", required=True)
    media.add_argument(
        "--profile",
        choices=[
            "TRAVEL_DOCUMENTARY",
            "TALKING_HEAD_EXPERT",
            "EXPLAINER_NEWS",
            "DIRECT_RECRUITMENT",
        ],
        default="TRAVEL_DOCUMENTARY",
    )
    media.add_argument("--target-seconds", type=float, default=60.0)
    media.add_argument("--title", default="")
    media.add_argument("--voice", type=Path)
    media.add_argument("--music", type=Path)
    media.add_argument("--project", type=Path, required=True)

    status = sub.add_parser("project-status")
    status.add_argument("--project", type=Path, required=True)

    validate = sub.add_parser("project-validate")
    validate.add_argument("--project", type=Path, required=True)
    validate.add_argument("--deep", action="store_true")

    patch = sub.add_parser("project-patch")
    patch.add_argument("--project", type=Path, required=True)
    patch.add_argument("--patch", type=Path, required=True)

    checkpoint = sub.add_parser("project-checkpoint")
    checkpoint.add_argument("--project", type=Path, required=True)
    checkpoint.add_argument("--label", default="manual")

    checkpoint_list = sub.add_parser("checkpoint-list")
    checkpoint_list.add_argument("--project", type=Path, required=True)

    checkpoint_restore = sub.add_parser("checkpoint-restore")
    checkpoint_restore.add_argument("--project", type=Path, required=True)
    checkpoint_restore.add_argument("--checkpoint", type=Path, required=True)

    media_audit = sub.add_parser("media-audit")
    media_audit.add_argument("--media", type=Path, action="append", required=True)

    source_review = sub.add_parser("source-review")
    source_review.add_argument("--media", type=Path, action="append", required=True)
    source_review.add_argument("--output-dir", type=Path, required=True)
    source_review.add_argument("--tiles", type=int, default=12)
    source_review.add_argument("--columns", type=int, default=4)
    source_review.add_argument("--candidate-seconds", type=float, default=3.4)

    review_mark = sub.add_parser("review-mark")
    review_mark.add_argument("--manifest", type=Path, required=True)
    review_mark.add_argument("--item", type=int, required=True)
    review_mark.add_argument("--candidate", type=int, required=True)
    review_mark.add_argument(
        "--decision",
        choices=["PENDING", "SHORTLIST", "KEEP", "REJECT"],
        required=True,
    )
    review_mark.add_argument("--role", default="")
    review_mark.add_argument("--note", default="")

    review_promote = sub.add_parser("review-promote")
    review_promote.add_argument("--manifest", type=Path, required=True)
    review_promote.add_argument("--project", type=Path, required=True)
    review_promote.add_argument("--item", type=int, required=True)
    review_promote.add_argument("--candidate", type=int, required=True)
    review_promote.add_argument("--role")
    review_promote.add_argument("--media-only", action="store_true")

    review_build = sub.add_parser("review-build")
    review_build.add_argument("--manifest", type=Path, required=True)
    review_build.add_argument("--project", type=Path, required=True)
    review_build.add_argument("--media-only", action="store_true")

    proxy_build = sub.add_parser("proxy-build")
    proxy_build.add_argument("--media", type=Path, action="append", required=True)
    proxy_build.add_argument("--force", action="store_true")

    shot_detect = sub.add_parser("shot-detect")
    shot_detect.add_argument("--media", type=Path, required=True)
    shot_detect.add_argument("--threshold", type=float, default=0.32)
    shot_detect.add_argument("--min-gap", type=float, default=0.45)
    shot_detect.add_argument("--force", action="store_true")

    sub.add_parser("cache-status")

    normalization_plan = sub.add_parser("normalization-plan")
    normalization_plan.add_argument("--media", type=Path, required=True)

    cache_prune = sub.add_parser("cache-prune")
    cache_prune.add_argument("--max-gb", type=float, default=20.0)

    hook_layout = sub.add_parser("hook-layout-apply")
    hook_layout.add_argument("--manifest", type=Path, required=True)
    hook_layout.add_argument("--project", type=Path, required=True)
    hook_layout.add_argument("--item", type=int, required=True)
    hook_layout.add_argument("--candidate", type=int, required=True)

    caption_plan = sub.add_parser("caption-plan")
    caption_plan.add_argument("--project", type=Path, required=True)
    caption_plan.add_argument("--coverage", type=float)

    caption_apply = sub.add_parser("caption-apply")
    caption_apply.add_argument("--project", type=Path, required=True)
    caption_apply.add_argument("--coverage", type=float)

    text_shot_report = sub.add_parser("text-shot-report")
    text_shot_report.add_argument("--project", type=Path, required=True)
    text_shot_report.add_argument("--coverage", type=float)

    text_shot_apply = sub.add_parser("text-shot-apply")
    text_shot_apply.add_argument("--project", type=Path, required=True)
    text_shot_apply.add_argument("--coverage", type=float)
    text_shot_apply.add_argument("--max-distance", type=int, default=3)

    transcript_set = sub.add_parser("transcript-set")
    transcript_set.add_argument("--project", type=Path, required=True)
    transcript_set.add_argument("--source", type=Path, required=True)

    story_optimize = sub.add_parser("story-optimize")
    story_optimize.add_argument("--project", type=Path, required=True)

    talk_rhythm = sub.add_parser("talk-rhythm-apply")
    talk_rhythm.add_argument("--project", type=Path, required=True)
    talk_rhythm.add_argument("--minimum-segment", type=float, default=1.2)
    talk_rhythm.add_argument("--punch-scale", type=float, default=1.035)

    review_status_parser = sub.add_parser("review-status")
    review_status_parser.add_argument("--project", type=Path, required=True)

    review_set = sub.add_parser("review-set")
    review_set.add_argument("--project", type=Path, required=True)
    review_set.add_argument("--stage", choices=["visual", "audio", "full"], required=True)
    review_set.add_argument(
        "--value",
        choices=["PENDING", "PASS", "FAIL"],
        required=True,
    )

    review_reset = sub.add_parser("review-reset")
    review_reset.add_argument("--project", type=Path, required=True)

    audio_analyze = sub.add_parser("audio-analyze")
    audio_analyze.add_argument("--file", type=Path, required=True)

    audio_master = sub.add_parser("audio-auto-master")
    audio_master.add_argument("--project", type=Path, required=True)

    qa_analyze = sub.add_parser("qa-analyze")
    qa_analyze.add_argument("--project", type=Path, required=True)
    qa_analyze.add_argument("--output", type=Path, required=True)
    qa_analyze.add_argument("--preview", action="store_true")

    optimize_all = sub.add_parser("optimize-all")
    optimize_all.add_argument("--project", type=Path, required=True)
    optimize_all.add_argument("--output", type=Path)
    optimize_all.add_argument("--preview", action="store_true")
    optimize_all.add_argument("--no-render", action="store_true")
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
                json.dumps(
                    {
                        "status": "TECHNICAL_DONE",
                        "output": str(result),
                        "review": "PENDING_PLAYBACK",
                    },
                    ensure_ascii=False,
                )
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

        if command == "media-import":
            project = ProjectState(
                profile=args.profile,
                target_seconds=max(10.0, float(args.target_seconds)),
                title=str(args.title or "").strip(),
                source_mode="DIRECT_MEDIA",
            )
            media_paths = [path.expanduser().resolve() for path in args.media]
            project.media = import_media(media_paths)
            if args.voice:
                voice = args.voice.expanduser().resolve()
                project.voiceover = str(voice)
                voice_seconds = probe_duration(voice)
                if args.profile == "TRAVEL_DOCUMENTARY":
                    project.target_seconds = max(
                        45.0,
                        min(90.0, voice_seconds + 6.0),
                    )
                elif args.profile == "TALKING_HEAD_EXPERT":
                    project.target_seconds = max(10.0, min(90.0, voice_seconds))
            if args.music:
                project.music = str(args.music.expanduser().resolve())
            project.timeline = build_rough_cut(project)
            if not project.timeline:
                raise ValueError("Không tạo được rough cut từ media đã chọn.")
            project.dirty = True
            return _save_result(project, args.project, project.source_mode)

        if command == "project-status":
            project = ProjectState.load(args.project.expanduser().resolve())
            _safe_print(
                json.dumps(
                    {
                        "status": "READY",
                        "project": str(args.project.expanduser().resolve()),
                        "profile": project.profile,
                        "source_mode": project.source_mode or "DIRECT_MEDIA",
                        "media": len(project.media),
                        "scenes": len(project.timeline),
                        "texts": len(project.texts),
                        "sfx": len(project.sfx),
                        "duration": round(
                            sum(item.duration for item in project.timeline),
                            3,
                        ),
                        "voiceover": bool(project.voiceover),
                        "music": bool(project.music),
                        "title": project.title,
                        "revision": project.revision,
                        "content_revision": project.content_revision,
                        "review": review_status(project),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "project-validate":
            path = args.project.expanduser().resolve()
            project = ProjectState.load(path)
            report = validate_project(project, deep=bool(args.deep))
            _safe_print(
                json.dumps(
                    {
                        "status": "PASS" if report.passed else "FAIL",
                        "project": str(path),
                        **report.to_dict(),
                    },
                    ensure_ascii=False,
                )
            )
            return 0 if report.passed else 1

        if command == "project-patch":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            checkpoint = create_checkpoint(
                project,
                project_path,
                label="before-patch",
            )
            patched = apply_patch(project, load_patch(args.patch))
            patched.save(project_path)
            report = validate_project(patched, deep=False)
            _safe_print(
                json.dumps(
                    {
                        "status": "DONE",
                        "project": str(project_path),
                        "checkpoint": str(checkpoint),
                        "warnings": [item.message for item in report.warnings],
                        "duration": report.duration,
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "project-checkpoint":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            checkpoint = create_checkpoint(
                project,
                project_path,
                label=str(args.label or "manual"),
            )
            _safe_print(
                json.dumps(
                    {
                        "status": "DONE",
                        "project": str(project_path),
                        "checkpoint": str(checkpoint),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "checkpoint-list":
            project_path = args.project.expanduser().resolve()
            items = list_checkpoints(project_path)
            _safe_print(
                json.dumps(
                    {
                        "status": "READY",
                        "project": str(project_path),
                        "checkpoints": [str(item) for item in items],
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "checkpoint-restore":
            project_path = args.project.expanduser().resolve()
            restored = restore_checkpoint(
                args.checkpoint.expanduser().resolve(),
                project_path,
            )
            _safe_print(
                json.dumps(
                    {
                        "status": "DONE",
                        "project": str(project_path),
                        "profile": restored.profile,
                        "duration": round(
                            sum(item.duration for item in restored.timeline),
                            3,
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "media-audit":
            reports = []
            rejected = 0
            for raw in args.media:
                audit = audit_video(raw.expanduser().resolve())
                reports.append(
                    {
                        "path": str(audit.path),
                        "score": audit.score,
                        "reject": audit.reject,
                        "reasons": list(audit.reasons),
                        "warnings": list(audit.warnings),
                        "needs_visual_review": audit.needs_visual_review,
                    }
                )
                if audit.reject:
                    rejected += 1
            _safe_print(
                json.dumps(
                    {
                        "status": "PASS" if rejected == 0 else "FILTERED",
                        "count": len(reports),
                        "rejected": rejected,
                        "items": reports,
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "source-review":
            manifest = build_source_review(
                [item.expanduser().resolve() for item in args.media],
                args.output_dir.expanduser().resolve(),
                tiles=max(1, min(24, int(args.tiles))),
                columns=max(1, min(6, int(args.columns))),
                candidate_seconds=max(0.5, float(args.candidate_seconds)),
            )
            _safe_print(
                json.dumps(
                    {
                        "status": "READY_FOR_VISUAL_REVIEW",
                        "manifest": str(manifest),
                        "auto_accept_visual": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "review-mark":
            manifest = mark_candidate_review(
                args.manifest.expanduser().resolve(),
                item_index=int(args.item),
                candidate_index=int(args.candidate),
                decision=str(args.decision),
                role=str(args.role or ""),
                note=str(args.note or ""),
            )
            _safe_print(
                json.dumps(
                    {
                        "status": "DONE",
                        "manifest": str(manifest),
                        "item": int(args.item),
                        "candidate": int(args.candidate),
                        "decision": str(args.decision).upper(),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "review-promote":
            result = promote_review_candidate(
                args.manifest.expanduser().resolve(),
                args.project.expanduser().resolve(),
                item_index=int(args.item),
                candidate_index=int(args.candidate),
                role=str(args.role).strip() if args.role else None,
                to_timeline=not bool(args.media_only),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "review-build":
            result = apply_kept_candidates(
                args.manifest.expanduser().resolve(),
                args.project.expanduser().resolve(),
                build_timeline=not bool(args.media_only),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "proxy-build":
            items = []
            for raw in args.media:
                result = ensure_proxy(
                    raw.expanduser().resolve(),
                    force=bool(args.force),
                )
                items.append(
                    {
                        "source": result.source,
                        "proxy": result.proxy,
                        "reused": result.reused,
                        "width": result.width,
                        "height": result.height,
                        "fps": result.fps,
                    }
                )
            _safe_print(
                json.dumps(
                    {"status": "DONE", "items": items},
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "shot-detect":
            source = args.media.expanduser().resolve()
            proxy = ensure_proxy(source, force=False)
            shots = detect_shots(
                Path(proxy.proxy),
                threshold=float(args.threshold),
                min_gap=float(args.min_gap),
                force=bool(args.force),
            )
            _safe_print(
                json.dumps(
                    {
                        "status": "DONE",
                        "source": str(source),
                        "analysis_source": proxy.proxy,
                        "proxy_reused": proxy.reused,
                        "shots": [asdict(item) for item in shots],
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "cache-status":
            _safe_print(
                json.dumps(
                    {"status": "READY", **cache_summary()},
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "normalization-plan":
            plan = build_normalization_plan(args.media.expanduser().resolve())
            _safe_print(
                json.dumps(
                    {"status": "READY", **plan.to_dict()},
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "cache-prune":
            max_bytes = max(0.25, float(args.max_gb)) * 1024**3
            result = prune_cache(max_bytes=int(max_bytes))
            _safe_print(
                json.dumps(
                    {"status": "DONE", **result},
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "hook-layout-apply":
            result = apply_candidate_hook_layout(
                args.manifest.expanduser().resolve(),
                args.project.expanduser().resolve(),
                item_index=int(args.item),
                candidate_index=int(args.candidate),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "caption-plan":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            coverage = (
                float(args.coverage)
                if args.coverage is not None
                else float(project.caption_coverage_target)
            )
            blocks = project_caption_plan(
                project,
                coverage_target=coverage,
            )
            _safe_print(
                json.dumps(
                    {
                        "status": "READY",
                        "project": str(project_path),
                        "coverage_target": coverage,
                        "caption_blocks": len(blocks),
                        "display_seconds": round(
                            sum(block.duration for block in blocks),
                            3,
                        ),
                        "blocks": [block.to_dict() for block in blocks],
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "caption-apply":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            coverage = (
                float(args.coverage)
                if args.coverage is not None
                else float(project.caption_coverage_target)
            )
            result = apply_selective_captions_to_file(
                project_path,
                coverage_target=coverage,
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "text-shot-report":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            coverage = (
                float(args.coverage)
                if args.coverage is not None
                else float(project.caption_coverage_target)
            )
            result = build_text_shot_report(
                project,
                coverage_target=coverage,
            )
            result["project"] = str(project_path)
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "text-shot-apply":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            coverage = (
                float(args.coverage)
                if args.coverage is not None
                else float(project.caption_coverage_target)
            )
            result = apply_text_shot_matching_to_file(
                project_path,
                coverage_target=coverage,
                max_distance=max(1, min(8, int(args.max_distance))),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "transcript-set":
            project_path = args.project.expanduser().resolve()
            source = args.source.expanduser().resolve()
            transcript = source.read_text(encoding="utf-8-sig").strip()
            if not transcript:
                raise ValueError("Transcript đang trống.")
            project = ProjectState.load(project_path)
            checkpoint = create_checkpoint(
                project,
                project_path,
                label="before-transcript-set",
            )
            project.transcript = transcript
            project.dirty = True
            project.save(project_path)
            _safe_print(
                json.dumps(
                    {
                        "status": "DONE",
                        "project": str(project_path),
                        "checkpoint": str(checkpoint),
                        "revision": project.revision,
                        "characters": len(transcript),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "story-optimize":
            result = optimize_story_to_file(
                args.project.expanduser().resolve(),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "talk-rhythm-apply":
            result = apply_talk_rhythm_to_file(
                args.project.expanduser().resolve(),
                minimum_segment=max(0.8, float(args.minimum_segment)),
                punch_scale=max(1.0, min(1.08, float(args.punch_scale))),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "review-status":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            result = review_status(project)
            result["project"] = str(project_path)
            result["revision"] = project.revision
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "review-set":
            result = set_review_stage(
                args.project.expanduser().resolve(),
                stage=str(args.stage),
                value=str(args.value),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "review-reset":
            result = reset_review(
                args.project.expanduser().resolve(),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "audio-analyze":
            result = measure_loudness(
                args.file.expanduser().resolve(),
            )
            _safe_print(
                json.dumps(
                    {"status": "READY", **result.to_dict()},
                    ensure_ascii=False,
                )
            )
            return 0

        if command == "audio-auto-master":
            result = auto_balance_project_file(
                args.project.expanduser().resolve(),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "qa-analyze":
            project_path = args.project.expanduser().resolve()
            project = ProjectState.load(project_path)
            result = analyze_render(
                args.output.expanduser().resolve(),
                project,
                preview=bool(args.preview),
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0

        if command == "optimize-all":
            result = run_optimized_pipeline(
                args.project.expanduser().resolve(),
                render=not bool(args.no_render),
                preview=bool(args.preview),
                output=args.output.expanduser().resolve() if args.output else None,
            )
            _safe_print(json.dumps(result, ensure_ascii=False))
            return 0
    except Exception as exc:
        _safe_print(f"ERROR: {exc}", error=True)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
