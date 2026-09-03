"""Background execution queue consumer.

Orders are created and validated synchronously, then execution is performed by
the dedicated worker. This keeps manual clicks and strategy-triggered orders
from calling the broker directly from the web request.
"""

import asyncio
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from . import constants as c
from .engine import ExecutionEngine
from .models import ExecutionQueue

logger = logging.getLogger(__name__)


@shared_task(name="apps.execution.process_execution_queue")
def process_execution_queue(batch_size=10):
    """Claim and execute a bounded batch of ready orders."""
    now = timezone.now()
    processed = 0

    for _ in range(max(1, int(batch_size))):
        with transaction.atomic():
            entry = (
                ExecutionQueue.objects.select_for_update()
                .select_related("order")
                .filter(status__in=[c.QUEUE_STATUS_PENDING, c.QUEUE_STATUS_RETRY])
                .filter(models_q_next_retry(now))
                .order_by("priority", "created_at")
                .first()
            )
            if entry is None:
                break
            entry.status = c.QUEUE_STATUS_PROCESSING
            entry.attempts += 1
            entry.next_retry = None
            entry.save(update_fields=["status", "attempts", "next_retry", "updated_at"])

        try:
            asyncio.run(ExecutionEngine().execute(entry.order))
        except Exception as exc:
            logger.exception("execution_queue_order_failed", extra={"order_id": entry.order_id, "attempt": entry.attempts})
            entry.refresh_from_db()
            if entry.order.status in {c.ORDER_STATUS_FAILED, c.ORDER_STATUS_CANCELLED}:
                entry.status = c.QUEUE_STATUS_FAILED
                entry.next_retry = None
                entry.save(update_fields=["status", "next_retry", "updated_at"])
            else:
                delay = min(300, max(5, 2 ** min(entry.attempts, 8)))
                entry.mark_retry(delay_seconds=delay)
        else:
            entry.status = c.QUEUE_STATUS_DONE
            entry.next_retry = None
            entry.save(update_fields=["status", "next_retry", "updated_at"])
        processed += 1

    return processed


def models_q_next_retry(now):
    """Return a reusable Q expression for immediately runnable queue entries."""
    from django.db.models import Q
    return Q(next_retry__isnull=True) | Q(next_retry__lte=now)
