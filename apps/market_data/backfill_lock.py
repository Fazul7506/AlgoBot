"""Distributed dispatch locks for broker candle-backfill lifecycle operations."""

from django_redis import get_redis_connection


class BackfillDispatchLock:
    """Short-lived Redis lock preventing duplicate lifecycle dispatch/recovery."""

    def __init__(self, scope):
        self.scope = str(scope or "initial")
        self._lock = None

    def acquire(self):
        redis = get_redis_connection("default")
        self._lock = redis.lock(
            f"algobot:market-data:backfill-dispatch:{self.scope}",
            timeout=30,
            blocking=False,
        )
        if not self._lock.acquire(blocking=False):
            self._lock = None
            return False
        return True

    def release(self):
        if self._lock is None:
            return
        try:
            self._lock.release()
        finally:
            self._lock = None


def acquire_backfill_dispatch_lock(scope):
    lock = BackfillDispatchLock(scope)
    if not lock.acquire():
        return None
    return lock