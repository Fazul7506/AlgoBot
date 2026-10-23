from django.test import SimpleTestCase

from apps.analysis.views import _as_items, _select_validated_contract


class ValidatedContractSelectionTests(SimpleTestCase):
    def setUp(self):
        self.capabilities = {
            "available": [
                {
                    "underlying_symbol": "R_100",
                    "contract_type": "PUT",
                    "contract_category": "callput",
                    "expiry_type": "intraday",
                    "sentiment": "down",
                },
                {
                    "underlying_symbol": "R_100",
                    "contract_type": "CALL",
                    "contract_category": "callput",
                    "expiry_type": "intraday",
                    "sentiment": "up",
                },
                {
                    "underlying_symbol": "R_100",
                    "contract_type": "MULTUP",
                    "contract_category": "multiplier",
                    "expiry_type": "intraday",
                    "sentiment": "up",
                },
            ]
        }

    def test_buy_selects_one_broker_published_contract(self):
        selected = _select_validated_contract(self.capabilities, direction="BUY", timeframe="M1")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["contract_type"], "CALL")
        self.assertEqual(selected["contract_family"], "callput")
        self.assertEqual(selected["source"], "deriv_contracts_for")

    def test_sell_selects_one_direction_compatible_contract(self):
        selected = _select_validated_contract(self.capabilities, direction="SELL", timeframe="M1")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["contract_type"], "PUT")
        self.assertEqual(selected["contract_family"], "callput")

    def test_no_direction_does_not_invent_a_contract(self):
        self.assertIsNone(_select_validated_contract(self.capabilities, direction=None, timeframe="M1"))


class BrokerPayloadTypeSafetyTests(SimpleTestCase):
    def test_scalar_barrier_is_normalized_to_one_item(self):
        self.assertEqual(_as_items(5), [5])

    def test_collection_barriers_remain_a_collection(self):
        self.assertEqual(_as_items([1, "2"]), [1, "2"])

    def test_missing_barriers_normalize_to_empty_collection(self):
        self.assertEqual(_as_items(None), [])
