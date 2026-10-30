from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.market_data.services import TickService
from apps.market_data.serializers import MarketSnapshotSerializer
from apps.market_data.validators import ValidationService


class BidAskProvenanceTests(SimpleTestCase):
    def validate(self, payload):
        symbol = SimpleNamespace(symbol="R_100")
        latest = MagicMock()
        latest.order_by.return_value.first.return_value = None
        with patch("apps.market_data.validators.MarketSymbol.objects.get", return_value=symbol), patch(
            "apps.market_data.validators.Tick.objects.filter", return_value=latest
        ):
            return ValidationService().validate_tick({"symbol": "R_100", "epoch": 100, "quote": "100", **payload})

    def test_missing_bid_and_ask_remain_unavailable(self):
        clean = self.validate({})
        self.assertIsNone(clean["bid"])
        self.assertIsNone(clean["ask"])
        self.assertEqual(clean["bid_ask_source"], "unavailable")

    def test_partial_bid_ask_preserves_only_the_supplied_side(self):
        clean = self.validate({"bid": "99.9"})
        self.assertEqual(clean["bid"], Decimal("99.9"))
        self.assertIsNone(clean["ask"])
        self.assertEqual(clean["bid_ask_source"], "partial")

    def test_complete_bid_ask_is_marked_as_broker_provided(self):
        clean = self.validate({"bid": "99.9", "ask": "100.1"})
        self.assertEqual(clean["bid"], Decimal("99.9"))
        self.assertEqual(clean["ask"], Decimal("100.1"))
        self.assertEqual(clean["bid_ask_source"], "broker")

    def test_legacy_unknown_bid_ask_values_are_not_serialized_as_real_quotes(self):
        tick = SimpleNamespace(
            symbol=SimpleNamespace(symbol="R_100"),
            bid=Decimal("100"), ask=Decimal("100"), quote=Decimal("100"),
            spread=Decimal("0"), epoch=100, volume=Decimal("0"),
            bid_ask_source="unknown",
        )
        payload = TickService().serialize(tick)
        self.assertIsNone(payload["bid"])
        self.assertIsNone(payload["ask"])
        self.assertIsNone(payload["spread"])
        self.assertFalse(payload["bid_ask_available"])

    def test_only_complete_broker_quotes_produce_a_spread(self):
        tick = SimpleNamespace(
            symbol=SimpleNamespace(symbol="R_100"),
            bid=Decimal("99.9"), ask=Decimal("100.1"), quote=Decimal("100"),
            spread=Decimal("0.2"), epoch=100, volume=Decimal("0"),
            bid_ask_source="broker",
        )
        payload = TickService().serialize(tick)
        self.assertEqual(payload["bid"], "99.9")
        self.assertEqual(payload["ask"], "100.1")
        self.assertEqual(payload["spread"], "0.2")
        self.assertTrue(payload["bid_ask_available"])

    def test_snapshot_serializer_hides_legacy_unverified_bid_ask(self):
        snapshot = SimpleNamespace(
            symbol=SimpleNamespace(symbol="R_100"),
            bid=Decimal("100"), ask=Decimal("100"), spread=Decimal("0"),
            bid_ask_source="unknown",
        )
        serializer = MarketSnapshotSerializer()
        self.assertIsNone(serializer.get_bid(snapshot))
        self.assertIsNone(serializer.get_ask(snapshot))
        self.assertIsNone(serializer.get_spread(snapshot))
        self.assertFalse(serializer.get_bid_ask_available(snapshot))

    def test_legacy_average_spread_is_not_exposed_without_verified_samples(self):
        from apps.market_data.serializers import MarketStatisticsSerializer

        serializer = MarketStatisticsSerializer()
        self.assertIsNone(serializer.get_average_spread(SimpleNamespace(
            average_spread=Decimal("0"), spread_sample_count=0
        )))
        self.assertEqual(serializer.get_average_spread(SimpleNamespace(
            average_spread=Decimal("0.2"), spread_sample_count=4
        )), "0.2")
