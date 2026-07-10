from __future__ import annotations

import time

import pytest

from mxh_publisher.services.lease import LeaseHeartbeat, LeaseHeartbeatError


class FakeRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def renew_lease(self, *_args, **_kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("database unavailable")


def test_heartbeat_renews_until_stopped() -> None:
    repository = FakeRepository()
    heartbeat = LeaseHeartbeat(
        repository,
        "delivery",
        "token",
        interval_seconds=0.01,
        max_consecutive_failures=1,
    ).start()
    time.sleep(0.04)
    heartbeat.stop()
    assert repository.calls >= 1


def test_heartbeat_surfaces_repeated_failure() -> None:
    repository = FakeRepository(fail=True)
    heartbeat = LeaseHeartbeat(
        repository,
        "delivery",
        "token",
        interval_seconds=0.01,
        max_consecutive_failures=1,
    ).start()
    time.sleep(0.03)
    with pytest.raises(LeaseHeartbeatError):
        heartbeat.stop()
