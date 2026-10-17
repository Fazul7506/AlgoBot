from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class BackfillDispatchLockTests(SimpleTestCase):
    @patch('apps.market_data.backfill_lock.get_redis_connection')
    def test_acquire_uses_non_blocking_scoped_lock(self, get_redis):
        lock = MagicMock()
        lock.acquire.return_value = True
        get_redis.return_value.lock.return_value = lock
        from apps.market_data.backfill_lock import acquire_backfill_dispatch_lock
        acquired = acquire_backfill_dispatch_lock('initial')
        self.assertIsNotNone(acquired)
        get_redis.return_value.lock.assert_called_once_with('algobot:market-data:backfill-dispatch:initial', timeout=30, blocking=False)
        lock.acquire.assert_called_once_with(blocking=False)
        acquired.release()
        lock.release.assert_called_once_with()

    @patch('apps.market_data.backfill_lock.get_redis_connection')
    def test_busy_lock_is_not_retried(self, get_redis):
        lock = MagicMock()
        lock.acquire.return_value = False
        get_redis.return_value.lock.return_value = lock
        from apps.market_data.backfill_lock import acquire_backfill_dispatch_lock
        self.assertIsNone(acquire_backfill_dispatch_lock('initial'))
        lock.release.assert_not_called()
    @patch('apps.market_data.backfill_lock.get_redis_connection', side_effect=ConnectionError("rediss://user:secret@redis.example:6379/0"))
    def test_redis_connection_failure_propagates_without_fabricating_a_lock(self, get_redis):
        from apps.market_data.backfill_lock import acquire_backfill_dispatch_lock

        with self.assertRaises(ConnectionError):
            acquire_backfill_dispatch_lock("initial")
        get_redis.assert_called_once_with("default")

    @patch('apps.market_data.backfill_lock.get_redis_connection')
    def test_release_failure_is_sanitized_and_does_not_mask_dispatch_result(self, get_redis):
        lock = MagicMock()
        lock.acquire.return_value = True
        lock.release.side_effect = ConnectionError("rediss://user:secret@redis.example:6379/0")
        get_redis.return_value.lock.return_value = lock
        from apps.market_data.backfill_lock import acquire_backfill_dispatch_lock

        acquired = acquire_backfill_dispatch_lock("initial")
        with patch("apps.market_data.backfill_lock.logger.warning") as warning:
            acquired.release()

        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[0], "backfill_dispatch_lock_release_failed")
        self.assertNotIn("secret", repr(warning.call_args))
        self.assertIsNone(acquired._lock)
