from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Invoice, Payment, Subscription
from core.services.payment_reconciler import PaymentReconciler
from core.services.payment_service import PaymentService
from core.views_billing import _reconcile_invoice


class BillingHardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="billing-user", password="pass12345")
        self.client.login(username="billing-user", password="pass12345")
        self.api_headers = {"HTTP_ORIGIN": "http://testserver"}

    def test_provider_return_pages_are_public_and_direct_navigation_is_protected(self):
        self.client.logout()
        response = self.client.get(reverse("billing_success_page"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("billing_success_page") + "?provider=intasend&reference=unknown")
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("billing_cancel_page"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("billing_cancel_page") + "?provider=intasend")
        self.assertEqual(response.status_code, 200)

    @patch("core.views_billing.PaymentService.get_intasend_payment_status")
    def test_intasend_nested_invoice_success_activates_subscription(self, get_status):
        invoice = Invoice.objects.create(user=self.user, amount_cents=99900, currency="KES", metadata={"plan": "BASIC", "provider": "intasend", "reference": "IS_TEST_123"}, external_id="IS-INVOICE-1")
        Payment.objects.create(user=self.user, invoice=invoice, external_id="IS-INVOICE-1", amount_cents=99900, currency="KES")
        get_status.return_value = {"invoice": {"invoice_id": "IS-INVOICE-1", "state": "COMPLETE", "currency": "KES", "value": "999.00"}, "meta": {}}
        result = _reconcile_invoice(invoice, "intasend")
        invoice.refresh_from_db()
        subscription = Subscription.objects.get(user=self.user)
        payment = Payment.objects.get(invoice=invoice)
        self.assertTrue(result["paid"])
        self.assertEqual(result["state"], "COMPLETE")
        self.assertTrue(invoice.paid)
        self.assertEqual(subscription.plan, "BASIC")
        self.assertTrue(subscription.is_active)
        self.assertTrue(subscription.expires_at > timezone.now())
        self.assertEqual(payment.status, "COMPLETED")

    @patch("core.views_billing.PaymentService.get_intasend_payment_status")
    def test_intasend_pending_return_does_not_upgrade_account(self, get_status):
        invoice = Invoice.objects.create(user=self.user, amount_cents=499900, currency="KES", metadata={"plan": "PRO", "provider": "intasend", "reference": "IS_TEST_PENDING"}, external_id="IS-INVOICE-2")
        Payment.objects.create(user=self.user, invoice=invoice, external_id="IS-INVOICE-2", amount_cents=499900, currency="KES")
        get_status.return_value = {"invoice": {"invoice_id": "IS-INVOICE-2", "state": "PENDING"}}
        result = _reconcile_invoice(invoice, "intasend")
        subscription = Subscription.objects.filter(user=self.user).first()
        self.assertFalse(result["paid"])
        self.assertEqual(result["state"], "PENDING")
        self.assertFalse(Invoice.objects.get(pk=invoice.pk).paid)
        self.assertTrue(subscription is None or subscription.plan == "FREE")

    @patch("core.views_billing.PaymentService.get_intasend_payment_status")
    def test_success_callback_reconciles_authenticated_owner(self, get_status):
        Invoice.objects.create(user=self.user, amount_cents=2499900, currency="KES", metadata={"plan": "ENTERPRISE", "provider": "intasend", "reference": "IS-CALLBACK-1"}, external_id="IS-INVOICE-3")
        get_status.return_value = {"invoice": {"invoice_id": "IS-INVOICE-3", "state": "COMPLETE"}}
        response = self.client.get(reverse("billing_success_page") + "?provider=intasend&reference=IS-CALLBACK-1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment confirmed")
        self.assertEqual(Subscription.objects.get(user=self.user).plan, "ENTERPRISE")

    def test_webhook_reconciler_uses_canonical_payment_states(self):
        metadata = {"api_ref": f"IS-{self.user.id}-BASIC-TEST123", "user_id": self.user.id, "plan": "BASIC", "currency": "KES"}
        first = PaymentReconciler.reconcile(provider="intasend", external_id="WEBHOOK-1", status="COMPLETE", amount="999.00", currency="KES", metadata=metadata)
        second = PaymentReconciler.reconcile(provider="intasend", external_id="WEBHOOK-1", status="COMPLETE", amount="999.00", currency="KES", metadata=metadata)
        payment = Payment.objects.get(external_id="WEBHOOK-1")
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(payment.status, "COMPLETED")
        self.assertEqual(Payment.objects.filter(external_id="WEBHOOK-1").count(), 1)
        self.assertEqual(Subscription.objects.get(user=self.user).plan, "BASIC")
        self.assertTrue(Subscription.objects.get(user=self.user).expires_at > timezone.now())

    def test_cancel_subscription_stops_renewal_without_removing_paid_access(self):
        expiry = timezone.now() + timedelta(days=12)
        subscription = Subscription.objects.get(user=self.user)
        subscription.plan = "PRO"
        subscription.price_cents = 499900
        subscription.currency = "kes"
        subscription.recurring = True
        subscription.is_active = True
        subscription.expires_at = expiry
        subscription.save(update_fields=["plan", "price_cents", "currency", "recurring", "is_active", "expires_at"])

        response = self.client.post(reverse("billing_cancel_subscription"), data={}, content_type="application/json", **self.api_headers)
        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertFalse(subscription.recurring)
        self.assertTrue(subscription.is_active)
        self.assertAlmostEqual(subscription.expires_at.timestamp(), expiry.timestamp(), delta=2)
        self.assertEqual(response.json()["status"], "cancelled_at_period_end")

    def test_expired_subscription_is_reported_inactive(self):
        subscription = Subscription.objects.get(user=self.user)
        subscription.plan = "PRO"
        subscription.price_cents = 499900
        subscription.currency = "kes"
        subscription.recurring = True
        subscription.is_active = True
        subscription.expires_at = timezone.now() - timedelta(minutes=1)
        subscription.save(update_fields=["plan", "price_cents", "currency", "recurring", "is_active", "expires_at"])

        response = self.client.get(reverse("billing_status"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["subscription"]["is_active"])
        self.assertFalse(Subscription.objects.get(user=self.user).is_active)

    @override_settings(BILLING_SUCCESS_URL="https://algobot.dpdns.org/billing/success/", BILLING_CANCEL_URL="https://algobot.dpdns.org/billing/cancel/", PESAPAL_CALLBACK_URL="https://algobot.dpdns.org/payments/pesapal/callback/")
    def test_explicit_provider_callback_urls_are_used(self):
        service = PaymentService()
        self.assertEqual(service._callback_url("BILLING_SUCCESS_URL", "/billing/success/", {"provider": "intasend", "reference": "IS-1-BASIC-X"}), "https://algobot.dpdns.org/billing/success?provider=intasend&reference=IS-1-BASIC-X")
        self.assertEqual(service._callback_url("BILLING_CANCEL_URL", "/billing/cancel/"), "https://algobot.dpdns.org/billing/cancel")
        self.assertEqual(service._callback_url("PESAPAL_CALLBACK_URL", "/payments/pesapal/callback/"), "https://algobot.dpdns.org/payments/pesapal/callback")
