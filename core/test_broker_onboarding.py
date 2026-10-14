from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from core.broker_onboarding import has_authorized_broker_connection

User = get_user_model()


class BrokerOnboardingGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="onboarding-user",
            email="onboarding@example.test",
            password="A-secure-test-password-123!",
        )
        self.broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
            supports_live=True,
        )

    def test_user_without_broker_connection_is_not_onboarded(self):
        self.assertFalse(has_authorized_broker_connection(self.user))

    def test_dashboard_redirects_to_broker_management_without_authorization(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard_page"))
        self.assertRedirects(
            response,
            reverse("broker_marketplace_page"),
            fetch_redirect_response=False,
        )

    def test_dashboard_renders_only_after_a_verified_connection_is_eligible(self):
        account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="V123456",
            status="active",
            token_status="active",
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=account,
            status="connected",
        )
        self.client.force_login(self.user)
        with patch.object(
            BrokerAccount,
            "is_connection_eligible",
            new_callable=PropertyMock,
            return_value=True,
        ):
            self.assertTrue(has_authorized_broker_connection(self.user))
            response = self.client.get(reverse("dashboard_page"))
        self.assertEqual(response.status_code, 200)

    def test_authenticated_login_page_does_not_skip_broker_setup(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("login_page"))
        self.assertRedirects(
            response,
            reverse("broker_marketplace_page"),
            fetch_redirect_response=False,
        )
