"""Shared contracts for social-network publisher adapters.

The contracts deliberately contain no credential fields.  Publishers receive
secrets from an injected provider at call time so a job can safely be persisted
without persisting an access token alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """A platform-neutral request to publish one approved video."""

    post_id: str | int
    video_path: Path
    caption: str
    scheduled_at_utc: datetime | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PublishResult:
    """Result returned after a platform accepted or verified a publish."""

    state: str
    remote_id: str | None = None
    permalink_url: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass(frozen=True, slots=True)
class PublishCheckpoint:
    """A remote identifier that must be durably saved before the next mutation."""

    platform: str
    post_id: str | int
    stage: str
    remote_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


PublishCheckpointCallback = Callable[[PublishCheckpoint], None]


class PublisherError(RuntimeError):
    """A stable, structured error exposed by publisher adapters.

    ``retryable`` means retrying the *same safe operation* can make progress.
    Callers must never retry a mutation when ``unknown_outcome`` is true;
    reconciliation must run first to avoid duplicate posts.
    """

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        unknown_outcome: bool = False,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.unknown_outcome = unknown_outcome
        self.metadata = dict(metadata or {})

    def as_dict(self) -> dict[str, Any]:
        """Return a log/IPC-friendly representation without credentials."""

        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "unknown_outcome": self.unknown_outcome,
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class Publisher(Protocol):
    """Minimal interface implemented by each platform adapter."""

    platform: str

    def publish(self, request: PublishRequest) -> PublishResult:
        """Publish an approved request or raise :class:`PublisherError`."""


__all__ = [
    "PublishCheckpoint",
    "PublishCheckpointCallback",
    "PublishRequest",
    "PublishResult",
    "Publisher",
    "PublisherError",
]
