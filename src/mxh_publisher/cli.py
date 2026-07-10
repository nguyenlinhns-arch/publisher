from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config, write_basic_config
from .logging_utils import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="MXHPublisher")
    parser.add_argument("--config", type=Path, help="Đường dẫn config.toml tùy chọn")
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("gui", help="Mở giao diện Windows")
    subparsers.add_parser("doctor", help="Kiểm tra môi trường")

    configure = subparsers.add_parser("configure-facebook", help="Lưu Page ID và token")
    configure.add_argument("--page-id", required=True)

    worker = subparsers.add_parser("worker", help="Chạy tác vụ nền")
    worker.add_argument("--verify-due", action="store_true")
    worker.add_argument("--max-items", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "gui"
    config = load_config(args.config)
    configure_logging(config.logs_dir, verbose=args.verbose)

    if command == "doctor":
        from .services.doctor import format_doctor, run_doctor

        checks = run_doctor(config)
        print(format_doctor(checks))
        return 1 if any(not check.passed and check.blocking for check in checks) else 0

    if command == "configure-facebook":
        if not str(args.page_id).isdigit():
            print("Page ID phải là số.", file=sys.stderr)
            return 2
        from .secrets import prompt_and_store_facebook_token

        write_basic_config(config, page_id=str(args.page_id))
        prompt_and_store_facebook_token()
        print("Đã lưu cấu hình Facebook. Chạy doctor để kiểm tra.")
        return 0

    from .repository import Repository

    repository = Repository(config.database_path)
    if command == "worker":
        if not args.verify_due:
            print("Worker V1 chỉ hỗ trợ --verify-due.", file=sys.stderr)
            return 2
        from .services.orchestrator import PublishingOrchestrator
        from .worker import verify_due

        orchestrator = PublishingOrchestrator(repository, config)
        try:
            count = verify_due(
                repository, orchestrator, max_items=max(1, args.max_items)
            )
            print(f"Đã đối soát {count} tác vụ Facebook.")
            return 0
        finally:
            orchestrator.close()

    from .ui.main_window import run_gui

    run_gui(config, repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
