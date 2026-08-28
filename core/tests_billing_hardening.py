from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Invoice, Payment, Subscription
from core.services.payment_reconciler import PaymentReconciler
from core.views_billing import _reconcile_invoice


class BillingHardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="billing-user", password="pass12345")
        self.client.login(username="billing-user", password="pass12345")

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
        invoice = Invoice.objects.create(
            user=self.user,
            amount_cents=99900,
            currency="KES",
            metadata={"plan": "BASIC", "provider": "intasend", "reference": "IS_TEST_123"},
            external_id="IS-INVOICE-1",
        )
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
        self.assertEqual(payment.status, "COMPLETED")

    @patch("core.views_billing.PaymentService.get_intasend_payment_status")
    def test_intasend_pending_return_does_not_upgrade_account(self, get_status):
        invoice = Invoice.objects.create(
            user=self.user,
            amount_cents=499900,
            currency="KES",
            metadata={"plan": "PRO", "provider": "intasend", "reference": "IS_TEST_PENDING"},
            external_id="IS-INVOICE-2",
        )
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
        Invoice.objects.create(
            user=self.user,
            amount_cents=2499900,
            currency="KES",
            metadata={"plan": "ENTERPRISE", "provider": "intasend", "reference": "IS-CALLBACK-1"},
            external_id="IS-INVOICE-3",
        )
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
