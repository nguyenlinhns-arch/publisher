from __future__ import annotations

import logging

from .repository import Repository
from .services.orchestrator import PublishingOrchestrator


LOGGER = logging.getLogger(__name__)


def verify_due(
    repository: Repository,
    orchestrator: PublishingOrchestrator,
    *,
    max_items: int = 20,
) -> int:
    repository.recover_expired_leases()
    processed = 0
    while processed < max_items:
        if not orchestrator.verify_one_due_facebook():
            break
        processed += 1
    LOGGER.info("Verification worker processed %s Facebook deliveries", processed)
    return processed
