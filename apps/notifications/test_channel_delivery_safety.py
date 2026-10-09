import base64
from datetime import timedelta
from email import message_from_bytes
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from .channel_service import _enc, send_gmail_notification, telegram_start, telegram_webhook
from .models import Notification, NotificationChannelConnection


class GmailDeliveryTests(TestCase):
    @override_settings(GOOGLE_CLIENT_ID="google-client", GOOGLE_CLIENT_SECRET="google-secret")
    @patch("apps.notifications.channel_service.requests.post")
    def test_gmail_delivery_uses_the_verified_gmail_oauth_account(self, post):
        user = get_user_model().objects.create_user(username="gmail-delivery-test", password="test-password")
        conn = NotificationChannelConnection.objects.create(
            user=user,
            provider="gmail",
            status="verified",
            address="verified@gmail.com",
            external_id="google-subject",
            access_token=_enc("valid-access"),
            refresh_token=_enc("valid-refresh"),
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        notification = Notification.objects.create(
            user=user,
            channel="gmail",
            title="Trade alert",
            message="A broker-confirmed event occurred.",
            category="trading",
        )
        response = Mock(status_code=200)
        response.json.return_value = {"id": "gmail-message-id"}
        post.return_value = response

        result = send_gmail_notification(conn, notification)

        self.assertEqual(result["id"], "gmail-message-id")
        self.assertEqual(post.call_args.args[0], "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer valid-access")
        raw = post.call_args.kwargs["json"]["raw"]
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        email = message_from_bytes(decoded)
        self.assertEqual(email["To"], "verified@gmail.com")
        self.assertIn("Trade alert", decoded.decode("utf-8"))
        self.assertIn("A broker-confirmed event occurred.", decoded.decode("utf-8"))

    @override_settings(GOOGLE_CLIENT_ID="google-client", GOOGLE_CLIENT_SECRET="google-secret")
    @patch("apps.notifications.channel_service.requests.post")
    def test_expired_gmail_access_token_is_refreshed_before_delivery(self, post):
        user = get_user_model().objects.create_user(username="gmail-refresh-test", password="test-password")
        conn = NotificationChannelConnection.objects.create(
            user=user,
            provider="gmail",
            status="verified",
            address="verified@gmail.com",
            external_id="google-subject-refresh",
            access_token=_enc("expired-access"),
            refresh_token=_enc("valid-refresh"),
            token_expires_at=timezone.now() - timedelta(minutes=1),
        )
        notification = Notification.objects.create(
            user=user, channel="gmail", title="Refresh test", message="Delivery", category="general"
        )
        refresh_response = Mock(status_code=200)
        refresh_response.json.return_value = {"access_token": "new-access", "expires_in": 3600}
        send_response = Mock(status_code=200)
        send_response.json.return_value = {"id": "refreshed-message"}
        post.side_effect = [refresh_response, send_response]

        result = send_gmail_notification(conn, notification)

        self.assertEqual(result["id"], "refreshed-message")
        self.assertIn("oauth2.googleapis.com/token", post.call_args_list[0].args[0])
        self.assertEqual(post.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer new-access")
        conn.refresh_from_db()
        self.assertEqual(conn.access_token, _enc("new-access"))
        self.assertGreater(conn.token_expires_at, timezone.now())


class TelegramBindingSafetyTests(TestCase):
    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_BOT_USERNAME="")
    def test_missing_bot_username_does_not_create_a_stale_pending_connection(self):
        user = get_user_model().objects.create_user(username="telegram-config-test", password="test-password")
        request = RequestFactory().get("/")
        request.session = {}
        with self.assertRaisesRegex(RuntimeError, "TELEGRAM_BOT_USERNAME"):
            telegram_start(user, request)
        self.assertFalse(NotificationChannelConnection.objects.filter(user=user, provider="telegram").exists())

    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook")
    def test_one_telegram_chat_cannot_be_bound_to_two_users(self):
        first_user = get_user_model().objects.create_user(username="telegram-binding-one", password="test-password")
        second_user = get_user_model().objects.create_user(username="telegram-binding-two", password="test-password")
        NotificationChannelConnection.objects.create(
            user=first_user, provider="telegram", status="verified", external_id="same-chat"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                NotificationChannelConnection.objects.create(
                    user=second_user, provider="telegram", status="verified", external_id="same-chat"
                )

    @override_settings(TELEGRAM_BOT_TOKEN="123456:TEST", TELEGRAM_MODE="webhook")
    def test_verification_refuses_a_chat_already_bound_to_another_user(self):
        import hashlib

        first_user = get_user_model().objects.create_user(username="telegram-binding-existing", password="test-password")
        second_user = get_user_model().objects.create_user(username="telegram-binding-pending", password="test-password")
        NotificationChannelConnection.objects.create(
            user=first_user, provider="telegram", status="verified", external_id="555"
        )
        raw = "verification-token"
        pending = NotificationChannelConnection.objects.create(
            user=second_user,
            provider="telegram",
            status="pending",
            verification_code_hash=hashlib.sha256(raw.encode()).hexdigest(),
            verification_expires_at=timezone.now() + timedelta(minutes=5),
        )
        result = telegram_webhook({
            "update_id": 912340,
            "message": {"chat": {"id": 555, "username": "shared-chat"}, "text": f"/start {raw}"},
        })
        pending.refresh_from_db()
        self.assertEqual(pending.status, "pending")
        self.assertEqual(pending.external_id, "")
        self.assertIn("already linked", result["reply"]["text"])
