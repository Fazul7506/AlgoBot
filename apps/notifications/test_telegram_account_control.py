from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection, Order, Position
from .channel_service import telegram_webhook
from .models import NotificationChannelConnection, NotificationPreference


@override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook")
class TelegramAccountControlTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="telegram-account-test", password="test-password")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="CR123456",
            currency="USD",
            balance="1250.50",
            equity="1275.75",
            free_margin="1200.00",
            status="active",
        )
        BrokerConnection.objects.create(broker=self.broker, broker_account=self.account, status="connected")
        self.telegram = NotificationChannelConnection.objects.create(user=self.user, provider="telegram", status="verified", external_id="777")
        NotificationPreference.objects.create(user=self.user, channel="telegram", enabled=True)

    def test_account_command_returns_all_safe_account_details(self):
        result = telegram_webhook({"update_id": 2001, "message": {"chat": {"id": 777}, "text": "/account"}})
        text = result["reply"]["text"]
        self.assertIn("AlgoBot accounts (1)", text)
        self.assertIn("Deriv — CR123456", text)
        self.assertIn("Balance: 1,250.50 USD", text)
        self.assertIn("Equity: 1,275.75 USD", text)
        self.assertIn("Free margin: 1,200.00 USD", text)
        self.assertNotIn("access_token", text)
        self.assertNotIn("refresh_token", text)

    def test_accounts_alias_and_positions_are_available(self):
        result = telegram_webhook({"update_id": 2002, "message": {"chat": {"id": 777}, "text": "/accounts"}})
        self.assertIn("CR123456", result["reply"]["text"])
        Position.objects.create(
            broker=self.broker,
            account=self.account,
            symbol="frxEURUSD",
            direction="buy",
            size="1",
            entry_price="1.10000",
            current_price="1.10100",
            profit="10.00",
            status="open",
        )
        result = telegram_webhook({"update_id": 2003, "message": {"chat": {"id": 777}, "text": "/positions"}})
        self.assertIn("frxEURUSD BUY", result["reply"]["text"])

    def test_trades_command_is_scoped_to_linked_user(self):
        Order.objects.create(
            user=self.user,
            broker=self.broker,
            account=self.account,
            symbol="frxXAUUSD",
            direction="buy",
            order_type="market",
            status="executed",
            stake="10",
        )
        result = telegram_webhook({"update_id": 2004, "message": {"chat": {"id": 777}, "text": "/trades"}})
        self.assertIn("frxXAUUSD BUY", result["reply"]["text"])

    def test_disconnect_revokes_telegram_without_changing_broker_account(self):
        result = telegram_webhook({"update_id": 2005, "message": {"chat": {"id": 777}, "text": "/disconnect"}})
        self.telegram.refresh_from_db()
        self.account.refresh_from_db()
        preference = NotificationPreference.objects.get(user=self.user, channel="telegram")
        self.assertIn("DISCONNECTED", result["reply"]["text"])
        self.assertEqual(self.telegram.status, "revoked")
        self.assertEqual(self.telegram.external_id, "")
        self.assertFalse(preference.enabled)
        self.assertEqual(self.account.status, "active")
        self.assertTrue(self.account.connections.filter(status="connected").exists())

    def test_commands_are_available_after_verification(self):
        result = telegram_webhook({"update_id": 2006, "message": {"chat": {"id": 777}, "text": "/help"}})
        text = result["reply"]["text"]
        for command in ("/account", "/accounts", "/positions", "/trades", "/settings", "/ping", "/refresh", "/disconnect"):
            self.assertIn(command, text)
