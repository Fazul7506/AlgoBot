from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

from apps.market_data.models import MarketSymbol
from apps.market_data.web_views import market_catalogue


class MarketCatalogueCacheResilienceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="market-cache-user")
        self.request = RequestFactory().get("/markets/catalogue/")
        self.request.user = self.user
        MarketSymbol.objects.create(
            broker="deriv",
            symbol="TEST",
            display_name="Test Instrument",
            market="Derived Indices",
            is_active=True,
            is_tradable=True,
        )

    @patch("apps.market_data.web_views.cache.set", side_effect=RuntimeError("command not allowed when used memory > maxmemory"))
    @patch("apps.market_data.web_views.cache.get", side_effect=RuntimeError("command not allowed when used memory > maxmemory"))
    def test_persisted_catalogue_is_served_when_redis_read_and_write_fail(self, cache_get, cache_set):
        response = market_catalogue(self.request)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "backend_market_catalogue")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["symbols"][0]["symbol"], "TEST")
        cache_get.assert_called_once()
        cache_set.assert_called_once()
