from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount
from .models import MarketSymbol


class BrokerTickApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="market-test", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        BrokerAccount.objects.create(user=self.user, broker=self.broker, account_id="VRTC123", status="active", is_preferred=True)
        MarketSymbol.objects.create(symbol="TEST", display_name="Test", market="Derived Indices", is_active=True, is_tradable=True)
        self.client.force_authenticate(self.user)

    def test_broker_tick_accepts_get(self):
        with patch("apps.market_data.api.fetch_tick", return_value={"symbol": "TEST", "quote": 100.25, "epoch": 1}):
            response = self.client.get("/api/market/ticks/broker/?symbol=TEST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["broker"], "Deriv")
        self.assertEqual(response.json()["account_id"], "VRTC123")

    def test_broker_tick_accepts_post(self):
        with patch("apps.market_data.api.fetch_tick", return_value={"symbol": "TEST", "quote": 100.25, "epoch": 1}):
            response = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_broker_tick_requires_a_symbol(self):
        response = self.client.get("/api/market/ticks/broker/")
        self.assertEqual(response.status_code, 400)
