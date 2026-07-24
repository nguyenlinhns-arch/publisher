from __future__ import annotations

import pathlib
import sys
import traceback

_previous_hook = sys.excepthook


def _coin_v8_hook(exc_type, exc_value, exc_tb):
    try:
        target = pathlib.Path(__file__).resolve().parent / "status" / "runtime_error.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            encoding="utf-8",
        )
    except Exception:
        pass
    _previous_hook(exc_type, exc_value, exc_tb)


sys.excepthook = _coin_v8_hook
