from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class BotRuntimeContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="runtime-owner", password="test-password"
        )
        self.client.force_login(self.user)

    @patch("core.views_user_modules._account", return_value=None)
    def test_missing_account_is_offline_and_does_not_load_global_cluster_data(self, _account):
        response = self.client.get(reverse("deployment_center"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["account_connected"])
        self.assertNotIn("clusters", response.context)
        self.assertContains(response, "Offline")

    @patch(
        "core.views_user_modules._account",
        return_value=SimpleNamespace(
            is_connection_eligible=False,
            broker=SimpleNamespace(name="Disconnected broker"),
        ),
    )
    def test_existing_but_ineligible_account_is_not_shown_as_connected(self, _account):
        response = self.client.get(reverse("deployment_center"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["account_connected"])
        self.assertContains(response, "Needs attention")
        self.assertContains(response, "Disconnected broker")
