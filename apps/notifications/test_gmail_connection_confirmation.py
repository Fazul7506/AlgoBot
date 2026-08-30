from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import NotificationChannelConnection


class GmailConnectionConfirmationEmailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="gmail-confirmation-user",
            email="account@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)

    @patch("apps.notifications.channel_views.send_transactional_email")
    @patch("apps.notifications.channel_views.gmail_callback")
    def test_successful_gmail_connection_sends_confirmation_to_connected_address(
        self, gmail_callback_mock, send_email_mock
    ):
        connection = NotificationChannelConnection.objects.create(
            user=self.user,
            provider="gmail",
            status="verified",
            address="connected@gmail.com",
            external_id="google-subject",
        )
        gmail_callback_mock.return_value = connection
        send_email_mock.return_value = "brevo"

        response = self.client.get(
            reverse("gmail_callback"),
            {"code": "oauth-code", "state": "valid-state"},
        )

        self.assertRedirects(response, "/notifications/")
        send_email_mock.assert_called_once()
        kwargs = send_email_mock.call_args.kwargs
        self.assertEqual(kwargs["recipient"], "connected@gmail.com")
        self.assertEqual(
            kwargs["subject"],
            "AlgoBot Gmail notifications connected successfully",
        )
        self.assertEqual(kwargs["category"], "system")
        self.assertIn("successfully connected", kwargs["message"])
        self.assertEqual(
            kwargs["metadata"]["action_url"],
            "https://algobot.dpdns.org/notifications/",
        )

    @patch("apps.notifications.channel_views.send_transactional_email")
    @patch("apps.notifications.channel_views.gmail_callback")
    def test_email_delivery_failure_does_not_undo_successful_gmail_connection(
        self, gmail_callback_mock, send_email_mock
    ):
        connection = NotificationChannelConnection.objects.create(
            user=self.user,
            provider="gmail",
            status="verified",
            address="connected@gmail.com",
            external_id="google-subject",
        )
        gmail_callback_mock.return_value = connection
        send_email_mock.side_effect = RuntimeError("Brevo unavailable")

        response = self.client.get(
            reverse("gmail_callback"),
            {"code": "oauth-code", "state": "valid-state"},
        )

        self.assertRedirects(response, "/notifications/")
        connection.refresh_from_db()
        self.assertEqual(connection.status, "verified")
        self.assertEqual(connection.address, "connected@gmail.com")
        self.assertEqual(send_email_mock.call_count, 1)
