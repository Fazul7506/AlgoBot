"""Regression coverage for Redis maxmemory during market catalogue startup."""
from unittest.mock import patch

from django.test import SimpleTestCase
from redis.exceptions import OutOfMemoryError

from apps.market_data import deriv_sync


class MarketSyncRedisOutOfMemoryTests(SimpleTestCase):
    @patch("apps.market_data.deriv_sync.cache.delete")
    @patch("apps.market_data.deriv_sync.MarketSymbol.objects.filter")
    @patch("apps.market_data.deriv_sync._sync_one_symbol", return_value=True)
    @patch(
        "apps.market_data.deriv_sync.asyncio.run",
        return_value={"active_symbols": [{"symbol": "R_10"}]},
    )
    @patch(
        "apps.market_data.deriv_sync.cache.add",
        side_effect=OutOfMemoryError("command not allowed when used memory > maxmemory"),
    )
    def test_catalogue_sync_continues_without_optional_lock_on_redis_oom(
        self, cache_add, request, sync_one, queryset_filter, cache_delete
    ):
        queryset_filter.return_value.exclude.return_value.update.return_value = 0

        synced = deriv_sync.sync_active_symbols()

        self.assertEqual(synced, 1)
        cache_add.assert_called_once_with(deriv_sync.MARKET_SYNC_LOCK, "1", timeout=15)
        sync_one.assert_called_once()
        cache_delete.assert_not_called()

    @patch("apps.market_data.deriv_sync.cache.add", return_value=False)
    def test_existing_lock_still_prevents_duplicate_catalogue_sync(self, cache_add):
        with self.assertRaisesRegex(
            RuntimeError, "catalogue refresh is already in progress"
        ):
            deriv_sync.sync_active_symbols()
