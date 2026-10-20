from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from core.billing_entitlements import PLAN_ENTITLEMENTS, entitlement_payload, effective_plan, usage
from django.utils import timezone
from datetime import timedelta


class BillingEntitlementsContractTests(TestCase):
    def test_entitlements_endpoint_accepts_the_billing_page_bearer_token(self):
        user = get_user_model().objects.create_user(username="billing-api-user", password="test-password")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")

        response = client.get(reverse("billing_entitlements"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["current"]["plan"], "FREE")
        self.assertIn("usage", response.data["current"])

    def test_all_customer_plans_exist_and_enterprise_is_unlimited(self):
        self.assertEqual(set(PLAN_ENTITLEMENTS), {"FREE", "BASIC", "PRO", "ENTERPRISE"})
        enterprise = PLAN_ENTITLEMENTS["ENTERPRISE"]
        self.assertEqual(enterprise.api_daily, -1)
        self.assertEqual(enterprise.backtests_daily, -1)
        self.assertEqual(enterprise.predictions_daily, -1)
        self.assertEqual(enterprise.orders_daily, -1)
        self.assertEqual(enterprise.live_orders_daily, -1)

    def test_staff_effective_plan_is_enterprise(self):
        user = get_user_model().objects.create_user(username="billing-admin", password="test-password")
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        self.assertEqual(effective_plan(user).key, "ENTERPRISE")
        payload = entitlement_payload(user)
        self.assertTrue(payload["active"])
        self.assertTrue(payload["usage"]["orders"]["unlimited"])

    def test_usage_payload_declares_measurement_source(self):
        user = get_user_model().objects.create_user(username="billing-user", password="test-password")
        payload = entitlement_payload(user)
        self.assertEqual(payload["usage"]["orders"]["source"], "audit_log")
        self.assertEqual(payload["usage"]["broker_accounts"]["source"], "database")
        self.assertIn("no synthetic usage is generated", payload["reset_policy"]["measurement"].lower())


    def test_broker_account_usage_counts_connected_integrations_not_duplicate_account_rows(self):
        from apps.brokers.models import Broker, BrokerAccount, BrokerConnection

        user = get_user_model().objects.create_user(username="broker-capacity-user", password="test-password")
        deriv = Broker.objects.create(name="Capacity Deriv", broker_type="deriv", status="active")
        first = BrokerAccount.objects.create(user=user, broker=deriv, account_id="CAPACITY-1", status="active")
        second = BrokerAccount.objects.create(user=user, broker=deriv, account_id="CAPACITY-2", status="active")
        BrokerConnection.objects.create(broker=deriv, broker_account=first, status="connected")
        self.assertEqual(usage(user, "broker_accounts"), 1)

        # A duplicate Broker registry row with the same provider type is still
        # one integration, even if account records reference a different row.
        duplicate_deriv = Broker.objects.create(name="Legacy Deriv Registry Row", broker_type="deriv", status="active")
        duplicate_account = BrokerAccount.objects.create(user=user, broker=duplicate_deriv, account_id="CAPACITY-LEGACY", status="active")
        BrokerConnection.objects.create(broker=duplicate_deriv, broker_account=duplicate_account, status="connected")
        self.assertEqual(usage(user, "broker_accounts"), 1)

        # A second connected account row for the same integration must not
        # consume another slot, while a genuinely different broker does.
        BrokerConnection.objects.create(broker=deriv, broker_account=second, status="connected")
        self.assertEqual(usage(user, "broker_accounts"), 1)
        other = Broker.objects.create(name="Capacity Other Broker", broker_type="other", status="active")
        other_account = BrokerAccount.objects.create(user=user, broker=other, account_id="OTHER-1", status="active")
        BrokerConnection.objects.create(broker=other, broker_account=other_account, status="connected")
        self.assertEqual(usage(user, "broker_accounts"), 2)

        second.status = "disabled"
        second.save(update_fields=["status"])
        self.assertEqual(usage(user, "broker_accounts"), 2)

    def test_broker_account_usage_ignores_stale_or_revoked_connections(self):
        from apps.brokers.models import Broker, BrokerAccount, BrokerConnection

        user = get_user_model().objects.create_user(username="broker-stale-capacity-user", password="test-password")
        broker = Broker.objects.create(name="Stale Capacity Broker", broker_type="deriv", status="active")
        valid = BrokerAccount.objects.create(user=user, broker=broker, account_id="VALID-1", status="active", token_status="active")
        BrokerConnection.objects.create(broker=broker, broker_account=valid, status="connected")
        stale_token = BrokerAccount.objects.create(user=user, broker=broker, account_id="STALE-1", status="active", token_status="revoked")
        BrokerConnection.objects.create(broker=broker, broker_account=stale_token, status="connected")
        expired = BrokerAccount.objects.create(user=user, broker=broker, account_id="EXPIRED-1", status="active", token_status="active", expires_at=timezone.now() - timedelta(minutes=1))
        BrokerConnection.objects.create(broker=broker, broker_account=expired, status="connected")
        disabled_broker = Broker.objects.create(name="Disabled Capacity Broker", broker_type="deriv", status="inactive")
        inactive_provider = BrokerAccount.objects.create(user=user, broker=disabled_broker, account_id="INACTIVE-PROVIDER-1", status="active", token_status="active")
        BrokerConnection.objects.create(broker=disabled_broker, broker_account=inactive_provider, status="connected")

        self.assertEqual(usage(user, "broker_accounts"), 1)
