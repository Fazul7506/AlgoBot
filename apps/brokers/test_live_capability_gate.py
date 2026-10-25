from unittest import TestCase

from apps.brokers.models import Broker


class BrokerLiveCapabilityGateTests(TestCase):
    def test_scaffold_broker_cannot_claim_live_support_even_if_legacy_flag_is_true(self):
        broker = Broker(
            name="Scaffold broker",
            broker_type="binance",
            supports_live=True,
            metadata={"adapter_state": "scaffold"},
        )
        self.assertFalse(broker.is_live_trading_supported)
        self.assertEqual(broker.live_capability_status, "setup_required")

    def test_only_configured_production_broker_can_expose_live_support(self):
        broker = Broker(
            name="Deriv",
            broker_type="deriv",
            supports_live=True,
            metadata={"adapter_state": "production"},
        )
        self.assertTrue(broker.is_live_trading_supported)
        self.assertEqual(broker.live_capability_status, "production_supported")

    def test_deriv_live_support_flag_must_still_be_enabled(self):
        broker = Broker(name="Deriv", broker_type="deriv", supports_live=False, metadata={})
        self.assertFalse(broker.is_live_trading_supported)
        self.assertEqual(broker.live_capability_status, "disabled")
