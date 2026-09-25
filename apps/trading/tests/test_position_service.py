from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount, Position
from apps.execution.models import Order
from apps.execution.services import PositionService


class PositionServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("p@example.com", "p@example.com", "pass")
        self.broker = Broker.objects.create(name="B", broker_type="deriv")
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="P",
            currency="USD",
        )
        self.order = Order.objects.create(
            user=self.user,
            broker_account=self.account,
            symbol="R_50",
            direction="buy",
            order_type="market",
            stake=1,
            contract_type="CALL",
        )

    def test_open_and_close_position_uses_broker_contract(self):
        contract = {
            "contract_id": "991",
            "transaction_id": "TX-991",
            "contract_type": "CALL",
            "underlying_symbol": "R_50",
            "buy_price": "10",
            "bid_price": "10.5",
            "payout": "19",
            "profit": "0.5",
            "currency": "USD",
            "date_start": 1760000000,
        }
        pos = PositionService().open_position(self.order, broker_contract=contract)
        self.assertEqual(pos.contract_id, "991")
        self.assertEqual(pos.entry_price, Decimal("10"))

        final = {
            **contract,
            "status": "closed",
            "sell_spot": "11",
            "sell_spot_time": 1760000060,
            "profit": "1",
            "payout": "20",
            "is_sold": 1,
        }
        PositionService().close_position(pos, broker_contract=final)
        pos.refresh_from_db()
        self.assertEqual(pos.status, "closed")
        self.assertEqual(pos.profit, Decimal("1"))
        self.assertEqual(pos.exit_price, Decimal("11"))

    def test_close_without_broker_confirmation_is_rejected(self):
        pos = Position.objects.create(
            broker=self.broker,
            account=self.account,
            contract_id="992",
            symbol="R_50",
            contract_type="CALL",
            status="open",
        )
        with self.assertRaises(ValueError):
            PositionService().close_position(pos, broker_contract={"contract_id": "992", "status": "open"})
