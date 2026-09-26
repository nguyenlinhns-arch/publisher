from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import load_config
from .repository import Repository
from .services.linh_mxh_hub import (
    DualStreamRequest,
    LinhMXHError,
    OrchestratorDispatcher,
    schedule_video_dual_stream,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mxh_publisher.hub_direct_cli",
        description="Headless Linh MXH Hub action.",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only prepare the local schedule; do not dispatch to platforms.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(args.request_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise LinhMXHError("Request JSON must be an object.")
        request = DualStreamRequest.from_mapping(payload)
        config = load_config(args.config)
        repository = Repository(config.database_path)
        dispatcher = (
            None
            if args.local_only or not request.commit
            else OrchestratorDispatcher(repository, config)
        )
        receipt = schedule_video_dual_stream(
            repository,
            request,
            remote_dispatcher=dispatcher,
        )
        print(
            json.dumps(
                receipt.as_dict(),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if receipt.final_status in {
            "DONE",
            "DONE_EXISTING",
            "PREPARED",
            "PLANNED",
        }:
            return 0
        return 3
    except (LinhMXHError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "action": "schedule_video_dual_stream",
                    "final_status": "ERROR",
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
