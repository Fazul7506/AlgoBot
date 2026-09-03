from django.contrib.auth import get_user_model
from django.test import TestCase

from core.billing_entitlements import PLAN_ENTITLEMENTS, entitlement_payload, effective_plan


class BillingEntitlementsContractTests(TestCase):
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
