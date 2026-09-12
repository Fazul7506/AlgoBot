from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.analytics import views
from apps.market_data.models import MarketSymbol


class AnalyticsSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="analytics-smoke", password="test-pass-123"
        )
        self.client.force_login(self.user)
        cache.clear()

    def test_dashboard_renders_single_page_controller_and_embedded_markets(self):
        MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="synthetic_index",
        )
        response = self.client.get(reverse("analytics-dashboard"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertEqual(body.count('data-page-controller="analysis-v2"'), 1)
        self.assertEqual(body.count('id="main-content"'), 1)
        self.assertIn('id="analysis-markets-data"', body)
        self.assertIn("R_100", body)

    def test_analysis_markets_cache_is_reused(self):
        MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="synthetic_index",
        )
        with patch.object(
            views.MarketSymbol.objects,
            "filter",
            wraps=views.MarketSymbol.objects.filter,
        ) as query:
            first = views._analysis_markets()
            second = views._analysis_markets()
        self.assertEqual(first, second)
        self.assertEqual(query.call_count, 1)

    def test_analysis_data_cache_avoids_recalculation(self):
        market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100",
            market="synthetic_index",
        )
        with patch.object(
            views,
            "analyze_candles",
            return_value={"status": "ok", "candles": 0},
        ) as analyze:
            first = self.client.get(
                reverse("analysis-data"),
                {"symbol": market.symbol, "timeframe": "M1", "limit": 300},
            )
            second = self.client.get(
                reverse("analysis-data"),
                {"symbol": market.symbol, "timeframe": "M1", "limit": 300},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(analyze.call_count, 1)

    def test_analysis_market_endpoint_is_user_authenticated(self):
        response = self.client.get(reverse("analysis-markets"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["markets"], [])
