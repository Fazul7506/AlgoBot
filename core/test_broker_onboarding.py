from pathlib import Path
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from core.broker_onboarding import has_authorized_broker_connection
from core.models import UserProfile

User = get_user_model()


class BrokerOnboardingGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="onboarding-user",
            email="onboarding@example.test",
            password="A-secure-test-password-123!",
        )
        UserProfile.objects.update_or_create(user=self.user, defaults={"email_verified": True, "email_verified_at": timezone.now()})
        self.broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
            supports_live=True,
        )

    def test_user_without_broker_connection_is_not_onboarded(self):
        self.assertFalse(has_authorized_broker_connection(self.user))

    def test_account_and_operational_pages_remain_available_during_onboarding(self):
        self.client.force_login(self.user)
        # Account management and observability must work before a broker is
        # connected; only trading-workspace routes are gated by this middleware.
        for path in ("/settings/", "/profile/", "/operations/audit/", "/monitoring/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotEqual(response.status_code, 302)

    def test_broker_marketplace_remains_accessible_during_onboarding(self):
        self.client.force_login(self.user)
        response = self.client.get("/brokers/marketplace/")
        self.assertNotEqual(response.status_code, 302)

    def test_automation_workspaces_are_available_but_wait_for_broker_before_execution(self):
        self.client.force_login(self.user)
        # The automation UI may be inspected before broker onboarding, but its
        # own state must remain non-executable until a verified connection exists.
        for path, expected_text in (
            ("/workspace/automation/", "Waiting for broker connection"),
            ("/workspace/automation/workflow-templates/", "Connect a broker"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_text)

    def test_smart_money_trading_workspace_remains_gated_during_onboarding(self):
        self.client.force_login(self.user)
        response = self.client.get("/smart-money/")
        self.assertRedirects(
            response,
            reverse("broker_marketplace_page"),
            fetch_redirect_response=False,
        )

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


class BrokerMarketplaceDirectoryUiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="marketplace-directory-user",
            email="marketplace-directory@example.test",
            password="A-secure-test-password-123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"email_verified": True, "email_verified_at": timezone.now()},
        )
        self.deriv = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
            supports_live=True,
        )
        self.other = Broker.objects.create(
            name="Example Broker",
            broker_type="example",
            status="active",
            supports_live=True,
        )

    def test_marketplace_renders_directory_search_filters_and_broker_branding(self):
        self.client.force_login(self.user)
        response = self.client.get("/brokers/marketplace/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Broker Integrations")
        self.assertContains(response, 'data-broker-search')
        self.assertContains(response, 'data-broker-status-filter="connected"')
        self.assertContains(response, 'data-broker-status-filter="available"')
        self.assertContains(response, 'data-broker-status-filter="unavailable"')
        self.assertContains(response, "https://deriv.com/favicon.ico")
        self.assertContains(response, 'alt="Deriv icon"')
        self.assertContains(response, "Example Broker")
        self.assertContains(response, "Not supported yet")
        self.assertContains(response, "Connected Accounts")
        self.assertContains(response, "Broker Benefits")
        self.assertContains(response, "Quick Actions")
        self.assertContains(response, "Request a Broker")
        self.assertContains(response, 'data-broker-category=')
        self.assertContains(response, 'data-broker-no-connected')
        self.assertContains(response, 'broker_marketplace.css?v=20261020-marketplace2')
        css = (Path(__file__).resolve().parents[1] / "static" / "css" / "broker_marketplace.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:1100px)", css)
        self.assertIn("@media(max-width:760px)", css)
        self.assertIn("@media(max-width:520px)", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_marketplace_preserves_deriv_connect_route(self):
        self.client.force_login(self.user)
        response = self.client.get("/brokers/marketplace/")
        self.assertContains(response, 'href="/brokers/connect/"')

    def test_marketplace_preserves_deriv_disconnect_route_for_connected_account(self):
        account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.deriv,
            account_id="V987654",
            status="active",
            token_status="active",
        )
        BrokerConnection.objects.create(
            broker=self.deriv,
            broker_account=account,
            status="connected",
        )
        self.client.force_login(self.user)
        response = self.client.get("/brokers/marketplace/")
        self.assertContains(response, 'action="/api/deriv/disconnect/"')
        self.assertContains(response, "csrfmiddlewaretoken")
