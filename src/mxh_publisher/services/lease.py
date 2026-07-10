from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Literal, Protocol


LOGGER = logging.getLogger(__name__)


class LeaseRepository(Protocol):
    def renew_lease(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        lease_seconds: int = 300,
    ): ...


class LeaseHeartbeatError(RuntimeError):
    pass


@dataclass(slots=True)
class LeaseHeartbeat:
    """Renew a worker lease while a blocking remote upload is in flight."""

    repository: LeaseRepository
    delivery_id: str
    lease_token: str
    lease_seconds: int = 3600
    interval_seconds: float = 60.0
    max_consecutive_failures: int = 3
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _failure: BaseException | None = field(default=None, init=False)

    def start(self) -> "LeaseHeartbeat":
        if self._thread is not None:
            raise RuntimeError("Lease heartbeat was already started.")
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-heartbeat-{self.delivery_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _run(self) -> None:
        failures = 0
        while not self._stop.wait(self.interval_seconds):
            try:
                self.repository.renew_lease(
                    self.delivery_id,
                    self.lease_token,
                    lease_seconds=self.lease_seconds,
                )
                failures = 0
            except BaseException as exc:  # retained and surfaced on caller thread
                failures += 1
                LOGGER.warning(
                    "Lease heartbeat failed (%s/%s): %s",
                    failures,
                    self.max_consecutive_failures,
                    exc,
                    extra={"delivery_id": self.delivery_id},
                )
                if failures >= self.max_consecutive_failures:
                    self._failure = exc
                    self._stop.set()
                    return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, self.interval_seconds + 1.0))
            if self._thread.is_alive():
                raise LeaseHeartbeatError("Không dừng được luồng gia hạn lease.")
        if self._failure is not None:
            raise LeaseHeartbeatError(
                f"Không gia hạn được lease trong lúc upload: {self._failure}"
            ) from self._failure

    def __enter__(self) -> "LeaseHeartbeat":
        return self.start()

    def __exit__(self, exc_type, _exc, _traceback) -> Literal[False]:
        try:
            self.stop()
        except LeaseHeartbeatError:
            if exc_type is None:
                raise
            LOGGER.exception("Lease heartbeat also failed during remote error handling")
        return False
