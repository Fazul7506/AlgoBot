import time
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from trading.models.market import MarketSymbol
from trading.services.market_service import DataCacheManager


class MarketSeedTests(TestCase):
    def test_seed_is_idempotent_and_creates_canonical_catalogue(self):
        call_command("seed_markets")
        self.assertEqual(MarketSymbol.objects.count(), 8)
        first = set(MarketSymbol.objects.values_list("symbol", flat=True))
        call_command("seed_markets")
        self.assertEqual(MarketSymbol.objects.count(), 8)
        self.assertEqual(first, set(MarketSymbol.objects.values_list("symbol", flat=True)))


class MemoryCacheExpiryTests(TestCase):
    @patch("trading.services.market_service.settings.USE_REDIS", False)
    def test_price_expires_without_redis(self):
        cache = DataCacheManager()
        cache.set_price("R_10", 1.0, 1.1, expiry=1)
        self.assertIsNotNone(cache.get_price("R_10"))
        time.sleep(1.05)
        self.assertIsNone(cache.get_price("R_10"))
