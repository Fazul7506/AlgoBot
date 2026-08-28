from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import MarketSnapshot, MarketSymbol


class MarketScannerApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username="scanner-test", password="test-pass")
        self.client.force_authenticate(user)
        self.gainer = MarketSymbol.objects.create(symbol="GAIN", display_name="Gainer", market="Derived Indices", is_active=True, is_tradable=True)
        self.loser = MarketSymbol.objects.create(symbol="LOSS", display_name="Loser", market="Derived Indices", is_active=True, is_tradable=True)
        self.no_data = MarketSymbol.objects.create(symbol="NODATA", display_name="No Data", market="Derived Indices", is_active=True, is_tradable=True)
        MarketSnapshot.objects.create(symbol=self.gainer, last_price=101, high=105, low=95, change=1, change_percent=2.5, spread=.2, volume=100)
        MarketSnapshot.objects.create(symbol=self.loser, last_price=99, high=104, low=90, change=-1, change_percent=-3.0, spread=.4, volume=80)

    def test_scanner_returns_backend_snapshot_data(self):
        response = self.client.get("/api/market/scanner/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "broker_snapshot_store")
        symbols = [row["symbol"] for row in response.json()["results"]]
        self.assertIn("GAIN", symbols)
        self.assertIn("LOSS", symbols)
        self.assertIn("NODATA", symbols)

    def test_gainer_filter_excludes_non_positive_change(self):
        response = self.client.get("/api/market/scanner/?direction=gainers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["symbol"] for r in response.json()["results"]], ["GAIN"])

    def test_spread_filter_excludes_symbols_without_a_snapshot(self):
        response = self.client.get("/api/market/scanner/?max_spread=0.25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["symbol"] for r in response.json()["results"]], ["GAIN"])

    def test_invalid_filters_are_rejected(self):
        self.assertEqual(self.client.get("/api/market/scanner/?direction=sideways").status_code, 400)
        self.assertEqual(self.client.get("/api/market/scanner/?sort=unknown").status_code, 400)

    def test_scanner_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/market/scanner/").status_code, 401)
