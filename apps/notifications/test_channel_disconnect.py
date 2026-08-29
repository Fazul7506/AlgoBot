from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import NotificationChannelConnection, NotificationPreference


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
