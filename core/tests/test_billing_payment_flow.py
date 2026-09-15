from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import Invoice, Payment, Subscription
from core.services.payment_reconciler import PaymentReconciler
from core.services.payment_service import PaymentService
from core.views_billing import CheckoutPlan, _checkout


class BillingPaymentFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="billing-user",
            email="billing@example.com",
            first_name="Billing",
            last_name="User",
        )

    @override_settings(INTASEND_WEBHOOK_CHALLENGE="testnet")
    def test_intasend_webhook_reuses_checkout_invoice_when_provider_id_differs(self):
        reference = f"IS-{self.user.id}-BASIC-abc123"
        invoice = Invoice.objects.create(
            user=self.user,
            amount_cents=99900,
            currency="KES",
            metadata={"plan": "BASIC", "provider": "intasend", "reference": reference},
        )

        result = PaymentReconciler.handle_intasend_webhook(
            {
                "invoice_id": "PROVIDER-INVOICE-1",
                "state": "COMPLETE",
                "value": "999.00",
                "currency": "KES",
                "api_ref": reference,
                "challenge": "testnet",
            }
        )

        self.assertEqual(result["status"], "COMPLETED")
        invoice.refresh_from_db()
        self.assertEqual(invoice.pk, Invoice.objects.get(external_id="PROVIDER-INVOICE-1").pk)
        self.assertTrue(invoice.paid)
        self.assertEqual(Payment.objects.get(external_id="PROVIDER-INVOICE-1").status, "COMPLETED")
        self.assertEqual(Subscription.objects.get(user=self.user).plan, "BASIC")

    def test_reconcile_rejects_provider_amount_mismatch(self):
        reference = f"IS-{self.user.id}-BASIC-mismatch"
        invoice = Invoice.objects.create(
            user=self.user,
            amount_cents=99900,
            currency="KES",
            metadata={"plan": "BASIC", "provider": "intasend", "reference": reference},
        )

        result = PaymentReconciler.reconcile(
            provider="intasend",
            external_id="PROVIDER-INVOICE-2",
            status="COMPLETE",
            amount="1000.00",
            currency="KES",
            metadata={
                "api_ref": reference,
                "plan": "BASIC",
                "user_id": self.user.id,
            },
        )

        self.assertEqual(result["rejected"], "amount_mismatch")
        invoice.refresh_from_db()
        self.assertFalse(invoice.paid)
        self.assertFalse(Payment.objects.filter(external_id="PROVIDER-INVOICE-2").exists())

    def test_provider_http_errors_are_safe_and_actionable(self):
        self.assertIn("payment credentials", PaymentService._checkout_http_error(PaymentService.INTASEND, 401, {}))
        self.assertIn("merchant configuration", PaymentService._checkout_http_error(PaymentService.INTASEND, 400, {}))
        self.assertIn("temporarily unavailable", PaymentService._checkout_http_error(PaymentService.PESAPAL, 503, {}))
        self.assertNotIn("secret", PaymentService._checkout_http_error(PaymentService.PESAPAL, 401, {"error": "secret-value"}))

    @override_settings(PAYMENT_HTTP_TIMEOUT="not-a-number")
    def test_invalid_timeout_does_not_break_payment_service_initialization(self):
        self.assertEqual(PaymentService().timeout, 20)

    @override_settings(INTASEND_PUBLIC_KEY="ISPubKey_test")
    @patch("core.services.payment_service.requests.post")
    def test_unexpected_provider_json_does_not_raise_or_return_a_checkout_url(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = ["unexpected"]
        post.return_value = response

        result = PaymentService().create_intasend_checkout(self.user, CheckoutPlan(plan="BASIC", price_cents=99900))

        self.assertEqual(result["url"], "")
        self.assertIn("no checkout URL", result["error"])

    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session", return_value={"url": "javascript:alert(1)"})
    def test_checkout_rejects_non_http_provider_redirects(self, create_checkout):
        request = Mock(user=self.user)
        url, error = _checkout(request, "BASIC", "intasend")

        self.assertIsNone(url)
        self.assertIn("couldn't start", error)
        create_checkout.assert_called_once()

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_test",
        BILLING_SUCCESS_URL="https://algobot.dpdns.org/billing/success/",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_checkout_carries_internal_reference_in_return_url(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://checkout.example/pay"}
        post.return_value = response

        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=99900, currency="KES"),
        )

        self.assertEqual(result["url"], "https://checkout.example/pay")
        payload = post.call_args.kwargs["json"]
        self.assertIn("provider=intasend", payload["redirect_url"])
        self.assertIn(f"reference=IS-{self.user.id}-BASIC-", payload["redirect_url"])
