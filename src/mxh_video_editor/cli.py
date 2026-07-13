from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mxh_publisher.services.media import default_frame_path, find_ffmpeg, find_ffprobe

from .config import load_config
from .editor import render_video


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _hide_console(command: str) -> None:
    if sys.platform != "win32" or command != "gui":
        return
    try:
        import ctypes

        window = ctypes.windll.kernel32.GetConsoleWindow()  # type: ignore[attr-defined]
        if window:
            ctypes.windll.user32.ShowWindow(window, 0)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="MXHVideoEditor")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("gui", help="Mở giao diện sửa video")
    subparsers.add_parser("doctor", help="Kiểm tra FFmpeg và nền mặc định")
    render = subparsers.add_parser("render", help="Sửa một video bằng dòng lệnh")
    render.add_argument("--input", type=Path, required=True)
    render.add_argument("--title", required=True)
    render.add_argument("--output-dir", type=Path, required=True)
    render.add_argument("--frame", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    command = args.command or "gui"
    _hide_console(command)

    if command == "doctor":
        print(f"ffmpeg: {find_ffmpeg()}")
        print(f"ffprobe: {find_ffprobe()}")
        print(f"nền mặc định: {default_frame_path()}")
        return 0

    if command == "render":
        config = load_config(args.output_dir)
        result = render_video(config, args.input, args.title, frame_path=args.frame)
        print(result.path)
        return 0

    from .ui import run_gui

    run_gui(load_config())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

