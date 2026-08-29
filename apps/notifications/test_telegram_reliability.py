from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .channel_service import telegram_webhook
from .models import NotificationChannelConnection, TelegramUpdate
from .services import NotificationEngine


class TelegramWebhookReliabilityTests(TestCase):
    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook", TELEGRAM_WEBHOOK_SECRET="test-secret")
    def test_duplicate_update_is_processed_once(self):
        payload = {"update_id": 1001, "message": {"chat": {"id": 777}, "text": "/help"}}
        first = telegram_webhook(payload)
        second = telegram_webhook(payload)
        self.assertTrue(first["processed"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(TelegramUpdate.objects.filter(update_id=1001).count(), 1)

    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook", TELEGRAM_WEBHOOK_SECRET="test-secret")
    def test_start_verification_marks_connection_verified(self):
        import hashlib
        user = self._user()
        raw = "secure-start-token"
        conn = NotificationChannelConnection.objects.create(
            user=user,
            provider="telegram",
            status="pending",
            verification_code_hash=hashlib.sha256(raw.encode()).hexdigest(),
            verification_expires_at=timezone.now() + timedelta(minutes=5),
        )
        result = telegram_webhook({"update_id": 1002, "message": {"chat": {"id": 888, "username": "stepper"}, "text": f"/start {raw}"}})
        conn.refresh_from_db()
        self.assertEqual(conn.status, "verified")
        self.assertEqual(conn.external_id, "888")
        self.assertEqual(result["reply"]["method"], "sendMessage")

    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook", TELEGRAM_WEBHOOK_SECRET="test-secret")
    def test_webhook_rejects_missing_secret(self):
        response = Client().post("/api/notifications/telegram/webhook/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)

    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook", TELEGRAM_WEBHOOK_SECRET="test-secret")
    def test_webhook_accepts_secret_and_returns_fast_reply(self):
        response = Client().post(
            "/api/notifications/telegram/webhook/",
            data='{"update_id":1003,"message":{"chat":{"id":999},"text":"/help"}}',
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["method"], "sendMessage")

    @override_settings(USE_CELERY=True)
    @patch("apps.notifications.services.deliver_notification")
    def test_telegram_notifications_are_queued(self, deliver_notification):
        user = self._user()
        NotificationChannelConnection.objects.create(user=user, provider="telegram", status="verified", external_id="123")
        notices = NotificationEngine().publish(user, "Trade", "Executed", channels=["telegram"])
        self.assertEqual(notices[0].status, "queued")
        deliver_notification.delay.assert_called_once_with(notices[0].id)

    def _user(self):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.create_user(username="telegram-test", password="test-password")
