import logging

from django.db import transaction

from .models import Order, ExecutionLog, ExecutionQueue
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class OrderRepository:
    def create(self, **data):
        return Order.objects.create(**data)

    def get_for_user(self, user, pk):
        return Order.objects.get(pk=pk, user=user)


class ExecutionLogRepository:
    def log(self, order, event, status, message='', latency=None, broker_response=None):
        return ExecutionLog.objects.create(
            order=order,
            event=event,
            status=status,
            message=message,
            latency=latency,
            broker_response=broker_response or {},
        )

    async def alog(self, order, event, status, message='', latency=None, broker_response=None):
        """Async-safe execution log persistence for the async execution boundary."""
        return await sync_to_async(self.log, thread_sensitive=True)(
            order, event, status, message, latency, broker_response
        )


class ExecutionQueueRepository:
    @staticmethod
    def _dispatch_execution_queue():
        """Wake a worker after the queue row commits; Beat remains recovery only."""
        try:
            from .tasks import process_execution_queue

            process_execution_queue.apply_async(
                kwargs={"batch_size": 10},
                queue="celery",
                expires=25,
            )
        except Exception:
            # The durable DB queue remains authoritative. The periodic recovery
            # poll will pick up this row if Redis is temporarily unavailable.
            logger.exception("execution.queue.dispatch_failed")

    def enqueue(self, order, priority=5, queue_type='priority'):
        entry = ExecutionQueue.objects.update_or_create(
            order=order,
            defaults={
                'priority': priority,
                'queue_type': queue_type,
                'status': 'pending',
                # Failed/retried queue rows may retain a future retry deadline;
                # an explicit manual retry must become immediately claimable.
                'next_retry': None,
            },
        )[0]
        transaction.on_commit(self._dispatch_execution_queue)
        return entry
