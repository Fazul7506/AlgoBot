from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import NotificationChannelConnection, NotificationPreference
from .services import send_transactional_email, sender_for_category


class NotificationChannelDisconnectTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="notification-disconnect-user",
            email="notification-disconnect@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_gmail_disconnect_permanently_deletes_connection_and_preference(self):
        NotificationChannelConnection.objects.create(
            user=self.user,
            provider="gmail",
            status="verified",
            address="connected@example.com",
            external_id="google-subject",
            access_token="encrypted-access-token",
            refresh_token="encrypted-refresh-token",
            metadata={"name": "Connected User", "picture": "https://example.com/avatar"},
        )
        NotificationPreference.objects.create(user=self.user, channel="gmail", enabled=True)
        session = self.client.session
        session["algobot_gmail_oauth_state"] = "stale-oauth-state"
        session.save()

        response = self.client.post(reverse("gmail_disconnect"))

        self.assertRedirects(response, "/notifications/")
        self.assertFalse(
            NotificationChannelConnection.objects.filter(user=self.user, provider="gmail").exists()
        )
        self.assertFalse(
            NotificationPreference.objects.filter(user=self.user, channel="gmail").exists()
        )
        self.assertNotIn("algobot_gmail_oauth_state", self.client.session)

        status = self.client.get(reverse("notification_channels_status"))
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["channels"]["gmail"], {
            "connected": False,
            "status": "not_connected",
            "address": "",
        })

    def test_telegram_disconnect_permanently_deletes_connection_and_preference(self):
        NotificationChannelConnection.objects.create(
            user=self.user,
            provider="telegram",
            status="verified",
            address="@algobot_user",
            external_id="123456789",
            verification_code_hash="hashed-code",
            metadata={"first_name": "AlgoBot", "username": "algobot_user"},
        )
        NotificationPreference.objects.create(user=self.user, channel="telegram", enabled=True)
        session = self.client.session
        session["algobot_telegram_link"] = "https://t.me/algobot?start=token"
        session.save()

        response = self.client.post(reverse("telegram_disconnect"))

        self.assertRedirects(response, "/notifications/")
        self.assertFalse(
            NotificationChannelConnection.objects.filter(user=self.user, provider="telegram").exists()
        )
        self.assertFalse(
            NotificationPreference.objects.filter(user=self.user, channel="telegram").exists()
        )
        self.assertNotIn("algobot_telegram_link", self.client.session)

        status = self.client.get(reverse("notification_channels_status"))
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["channels"]["telegram"], {
            "connected": False,
            "status": "not_connected",
            "address": "",
        })


class BrandedNotificationEmailTests(TestCase):
    @override_settings(
        ALGOBOT_SECURITY_EMAIL="security@algobot.dpdns.org",
        ALGOBOT_SUPPORT_EMAIL="support@algobot.dpdns.org",
        ALGOBOT_NOREPLY_EMAIL="noreply@algobot.dpdns.org",
    )
    def test_sender_policy_routes_security_support_and_general(self):
        self.assertEqual(sender_for_category("security").email, "security@algobot.dpdns.org")
        self.assertEqual(sender_for_category("authentication").email, "security@algobot.dpdns.org")
        self.assertEqual(sender_for_category("billing").email, "support@algobot.dpdns.org")
        self.assertEqual(sender_for_category("support").email, "support@algobot.dpdns.org")
        self.assertEqual(sender_for_category("system").email, "noreply@algobot.dpdns.org")
        self.assertEqual(sender_for_category("general").email, "noreply@algobot.dpdns.org")

    @override_settings(
        BREVO_API_KEY="test-brevo-key",
        ALGOBOT_SECURITY_EMAIL="security@algobot.dpdns.org",
        ALGOBOT_SUPPORT_EMAIL="support@algobot.dpdns.org",
        ALGOBOT_NOREPLY_EMAIL="noreply@algobot.dpdns.org",
    )
    @patch("apps.notifications.services.requests.post")
    def test_brevo_payload_uses_category_sender_and_html(self, post):
        post.return_value = Mock(status_code=201, raise_for_status=Mock())

        provider = send_transactional_email(
            recipient="user@gmail.com",
            subject="Security alert",
            message="A new sign-in was detected.\nReview your account.",
            category="security",
            metadata={"action_url": "https://algobot.dpdns.org/security", "action_label": "Review account"},
        )

        self.assertEqual(provider, "brevo")
        post.assert_called_once()
        request = post.call_args.kwargs
        self.assertEqual(request["headers"]["api-key"], "test-brevo-key")
        self.assertEqual(request["json"]["sender"], {
            "name": "AlgoBot Security",
            "email": "security@algobot.dpdns.org",
        })
        self.assertEqual(request["json"]["to"], [{"email": "user@gmail.com"}])
        self.assertEqual(request["json"]["subject"], "Security alert")
        self.assertIn("<h1", request["json"]["htmlContent"])
        self.assertIn("Review account", request["json"]["htmlContent"])
        self.assertIn("A new sign-in was detected.<br>Review your account.", request["json"]["htmlContent"])

    @override_settings(
        BREVO_API_KEY="",
        ALGOBOT_SUPPORT_EMAIL="support@algobot.dpdns.org",
    )
    def test_django_fallback_still_uses_branded_html_sender(self):
        provider = send_transactional_email(
            recipient="user@example.com",
            subject="Support update",
            message="We have updated your request.",
            category="support",
        )

        self.assertEqual(provider, "django")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "AlgoBot Support <support@algobot.dpdns.org>")
        self.assertEqual(mail.outbox[0].to, ["user@example.com"])
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assertIn("AlgoBot Support", mail.outbox[0].alternatives[0][0])
