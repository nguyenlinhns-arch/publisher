from __future__ import annotations

import sys

from mxh_publisher.cli import configure_console_encoding


class FakeTextStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_console_streams_are_configured_for_utf8(monkeypatch) -> None:
    stdout = FakeTextStream()
    stderr = FakeTextStream()
    with monkeypatch.context() as context:
        context.setattr(sys, "stdout", stdout)
        context.setattr(sys, "stderr", stderr)
        configure_console_encoding()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]
