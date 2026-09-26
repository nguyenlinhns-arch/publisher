from __future__ import annotations

import argparse
import json
from pathlib import Path

from .host_bridge import HostBridge


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="linh-edit-engine")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capabilities")

    render = sub.add_parser("render")
    render.add_argument("--plan", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = HostBridge()
    if args.command == "capabilities":
        print(json.dumps(bridge.capabilities(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "render":
        print(
            json.dumps(
                bridge.render(args.plan, args.output),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
