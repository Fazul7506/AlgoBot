from __future__ import annotations

import asyncio
import logging
from functools import wraps

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django_redis import get_redis_connection
from django.utils import timezone

from apps.brokers.exceptions import BrokerAuthenticationError, BrokerConnectionError, BrokerOrderError
from . import constants as c
from .engine import ExecutionEngine
from .models import ExecutionQueue, Order

logger = logging.getLogger(__name__)


def _execution_queue_singleton(func):
    """Prevent overlapping execution-queue consumers across worker processes."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            redis = get_redis_connection("default")
            lock = redis.lock(
                "algobot:execution-queue:singleton",
                timeout=600,
                blocking=False,
            )
            acquired = lock.acquire(blocking=False)
        except Exception:
            # If Redis cannot provide the lock, fail closed rather than risking
            # concurrent execution consumers during a database incident.
            logger.exception("execution.queue.lock_unavailable")
            return {"processed": 0, "succeeded": 0, "failed": 0, "uncertain": 0}

        if not acquired:
            logger.info("execution.queue.overlap_skipped")
            return {"processed": 0, "succeeded": 0, "failed": 0, "uncertain": 0}

        try:
            return func(*args, **kwargs)
        finally:
            try:
                lock.release()
            except Exception:
                logger.exception("execution.queue.lock_release_failed")

    return wrapper


@shared_task(name="apps.execution.process_execution_queue")
@_execution_queue_singleton
def process_execution_queue(batch_size=10):
    """Claim queued orders and execute them once at the broker boundary."""
    now = timezone.now()
    limit = max(1, min(int(batch_size or 10), 100))
    processed = succeeded = failed = uncertain = 0

    for _ in range(limit):
        with transaction.atomic():
            entry = (
                ExecutionQueue.objects.select_for_update(skip_locked=True)
                .select_related("order", "order__user", "order__broker_account", "order__broker_account__broker")
                .filter(
                    Q(
                        status=c.QUEUE_STATUS_PENDING,
                        next_retry__isnull=True,
                    )
                    | Q(
                        status=c.QUEUE_STATUS_RETRY,
                        next_retry__lte=now,
                    )
                )
                .order_by("priority", "created_at")
                .first()
            )
            if entry is None:
                break
            entry.status = c.QUEUE_STATUS_PROCESSING
            entry.attempts += 1
            entry.next_retry = None
            entry.save(update_fields=["status", "attempts", "next_retry", "updated_at"])
            order_id = entry.order_id

        processed += 1
        order = Order.objects.select_related("user", "broker_account", "broker_account__broker").get(pk=order_id)
        try:
            asyncio.run(ExecutionEngine().execute(order))
            ExecutionQueue.objects.filter(pk=entry.pk).update(status=c.QUEUE_STATUS_DONE, next_retry=None, updated_at=timezone.now())
            succeeded += 1
            logger.info("execution.queue.completed order_id=%s attempt=%s", order_id, entry.attempts)
        except (BrokerConnectionError, asyncio.TimeoutError, TimeoutError) as exc:
            # A transport failure can happen after the broker accepted the order.
            # Leave the order explicitly uncertain; never blindly duplicate it.
            Order.objects.filter(pk=order_id).update(
                status=c.ORDER_STATUS_SENT,
                validation_context={**(order.validation_context or {}), "reconciliation_required": True, "execution_error": str(exc)[:500]},
                updated_at=timezone.now(),
            )
            ExecutionQueue.objects.filter(pk=entry.pk).update(status=c.QUEUE_STATUS_FAILED, updated_at=timezone.now())
            uncertain += 1
            logger.error("execution.queue.uncertain order_id=%s attempt=%s error=%s", order_id, entry.attempts, exc)
        except (BrokerAuthenticationError, BrokerOrderError, PermissionError, ValueError) as exc:
            Order.objects.filter(pk=order_id).update(status=c.ORDER_STATUS_FAILED, updated_at=timezone.now())
            ExecutionQueue.objects.filter(pk=entry.pk).update(status=c.QUEUE_STATUS_FAILED, updated_at=timezone.now())
            failed += 1
            logger.warning("execution.queue.rejected order_id=%s attempt=%s error=%s", order_id, entry.attempts, exc)
        except Exception as exc:
            # ExecutionEngine marks an order sent before calling the adapter.
            # Any unclassified failure after that boundary may have happened
            # after broker acceptance, so do not convert it to retryable failed.
            current_status = Order.objects.filter(pk=order_id).values_list("status", flat=True).first()
            if current_status in {c.ORDER_STATUS_SENT, c.ORDER_STATUS_ACCEPTED, c.ORDER_STATUS_EXECUTED}:
                current = Order.objects.filter(pk=order_id).only("validation_context").first()
                context = dict(current.validation_context or {}) if current else {}
                context.update({"reconciliation_required": True, "execution_error": str(exc)[:500]})
                Order.objects.filter(pk=order_id).update(
                    status=c.ORDER_STATUS_SENT,
                    validation_context=context,
                    updated_at=timezone.now(),
                )
                ExecutionQueue.objects.filter(pk=entry.pk).update(status=c.QUEUE_STATUS_FAILED, updated_at=timezone.now())
                uncertain += 1
                logger.exception("execution.queue.uncertain order_id=%s attempt=%s", order_id, entry.attempts)
            else:
                Order.objects.filter(pk=order_id).update(status=c.ORDER_STATUS_FAILED, updated_at=timezone.now())
                ExecutionQueue.objects.filter(pk=entry.pk).update(status=c.QUEUE_STATUS_FAILED, updated_at=timezone.now())
                failed += 1
                logger.exception("execution.queue.failed order_id=%s attempt=%s", order_id, entry.attempts)

    return {"processed": processed, "succeeded": succeeded, "failed": failed, "uncertain": uncertain}


@shared_task
def retry_failed_orders():
    return process_execution_queue()
