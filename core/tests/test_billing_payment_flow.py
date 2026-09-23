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
    @patch("core.services.payment_reconciler.PaymentService.get_intasend_payment_status")
    def test_intasend_webhook_reuses_checkout_invoice_when_provider_id_differs(self, get_status):
        reference = f"IS-{self.user.id}-BASIC-abc123"
        invoice = Invoice.objects.create(
            user=self.user,
            amount_cents=99900,
            currency="KES",
            metadata={"plan": "BASIC", "provider": "intasend", "reference": reference},
        )

        get_status.return_value = {"invoice": {"invoice_id": "PROVIDER-INVOICE-1", "state": "COMPLETE", "value": "999.00", "currency": "KES"}}

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

    @override_settings(INTASEND_PUBLIC_KEY="ISPubKey_test", INTASEND_API_BASE_URL="https://sandbox.intasend.com")
    @patch("core.services.payment_service.requests.post")
    def test_unexpected_provider_json_does_not_raise_or_return_a_checkout_url(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = ["unexpected"]
        post.return_value = response

        result = PaymentService().create_intasend_checkout(self.user, CheckoutPlan(plan="BASIC", price_cents=99900, recurring=False))

        self.assertEqual(result["url"], "")
        self.assertIn("no checkout URL", result["error"])

    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session", return_value={"url": "javascript:alert(1)"})
    def test_checkout_rejects_non_http_provider_redirects(self, create_checkout):
        request = Mock(user=self.user)
        url, error = _checkout(request, "BASIC", "intasend")

        self.assertIsNone(url)
        self.assertIn("Payment provider could not start checkout", error)
        create_checkout.assert_called_once()

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_test",
        INTASEND_API_BASE_URL="https://sandbox.intasend.com",
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
            CheckoutPlan(plan="BASIC", price_cents=99900, currency="KES", recurring=False),
        )

        self.assertEqual(result["url"], "https://checkout.example/pay")
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("&", payload["redirect_url"])
        self.assertNotIn("provider=", payload["redirect_url"])
        self.assertIn(f"reference=IS-{self.user.id}-BASIC-", payload["redirect_url"])

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_test",
        INTASEND_API_BASE_URL="https://sandbox.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_checkout_reuses_the_persisted_invoice_reference(self, post):
        response = Mock()
        response.ok = True
        response.headers = {}
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://checkout.example/pay"}
        post.return_value = response
        reference = f"IS-{self.user.id}-BASIC-invoice-ref"

        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=99900, currency="KES", reference=reference, recurring=False),
        )

        self.assertEqual(result["reference"], reference)
        self.assertEqual(post.call_args.kwargs["json"]["api_ref"], reference)
        self.assertIn(f"reference={reference}", post.call_args.kwargs["json"]["redirect_url"])

    @override_settings(INTASEND_PUBLIC_KEY="ISPubKey_test", INTASEND_API_BASE_URL="https://sandbox.intasend.com")
    @patch("core.services.payment_service.requests.post")
    def test_intasend_omits_unconfigured_merchant_tariffs(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://checkout.example/pay"}
        post.return_value = response

        PaymentService().create_intasend_checkout(self.user, CheckoutPlan(plan="BASIC", price_cents=99900, recurring=False))

        payload = post.call_args.kwargs["json"]
        self.assertNotIn("mobile_tarrif", payload)
        self.assertNotIn("card_tarrif", payload)

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_test",
        INTASEND_API_BASE_URL="https://sandbox.intasend.com",
        INTASEND_MOBILE_TARIFF="MOBILE-PAYS",
        INTASEND_CARD_TARIFF="CARD-PAYS",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_sends_configured_merchant_tariffs(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://checkout.example/pay"}
        post.return_value = response

        PaymentService().create_intasend_checkout(self.user, CheckoutPlan(plan="BASIC", price_cents=99900, recurring=False))

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["mobile_tarrif"], "MOBILE-PAYS")
        self.assertEqual(payload["card_tarrif"], "CARD-PAYS")

    @override_settings(INTASEND_PUBLIC_KEY="ISPubKey_test_example", INTASEND_API_BASE_URL="https://api.intasend.com")
    def test_intasend_rejects_test_key_on_live_api_endpoint(self):
        result = PaymentService().create_intasend_checkout(self.user, CheckoutPlan(plan="BASIC", price_cents=99900, recurring=False))
        self.assertEqual(result["url"], "")
        self.assertIn("sandbox API URL", result["error"])

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_live_example",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_http_500_is_classified_and_sanitized(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 500
        response.headers = {"X-Request-ID": "req-500"}
        response.json.return_value = {"error": "provider failure", "secret_key": "ISSecretKey_live_DO_NOT_LOG"}
        post.return_value = response

        with patch("core.services.payment_service.logger.error") as log_error:
            result = PaymentService().create_intasend_checkout(
                self.user,
                CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
            )

        self.assertEqual(result["error_classification"], "provider unavailable")
        self.assertIn("temporarily unavailable", result["error"])
        diagnostic = str(log_error.call_args)
        self.assertIn("req-500", diagnostic)
        self.assertIn("'amount': '500.00'", diagnostic)
        self.assertIn("'currency': 'KES'", diagnostic)
        self.assertNotIn("ISSecretKey_live_DO_NOT_LOG", diagnostic)
        self.assertNotIn("X-IntaSend-Public-API-Key", diagnostic)

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_live_example",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_http_400_and_422_are_classified_as_malformed_request(self, post):
        for status_code in (400, 422):
            response = Mock()
            response.ok = False
            response.status_code = status_code
            response.headers = {}
            response.json.return_value = {"detail": "invalid checkout payload"}
            post.return_value = response
            result = PaymentService().create_intasend_checkout(
                self.user,
                CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
            )
            self.assertEqual(result["error_classification"], "malformed request")

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_live_example",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_timeout_is_classified_without_retrying_post(self, post):
        from requests import Timeout
        post.side_effect = Timeout("timeout")
        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
        )
        self.assertEqual(result["error_classification"], "timeout/network failure")
        self.assertEqual(post.call_count, 1)

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_live_example",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_basic_50000_kes_payload_uses_major_units_and_supported_fields(self, post):
        response = Mock()
        response.ok = True
        response.status_code = 201
        response.headers = {}
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://checkout.example/pay"}
        post.return_value = response

        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
        )
        self.assertEqual(result["url"], "https://checkout.example/pay")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["amount"], "500.00")
        self.assertEqual(payload["currency"], "KES")
        self.assertEqual(payload["channel"], "WEBSITE")
        self.assertTrue(payload["redirect_url"].startswith("https://"))
        self.assertNotIn("recurring", payload)
        self.assertNotIn("mobile_tarrif", payload)
        self.assertNotIn("card_tarrif", payload)
        self.assertEqual(post.call_args.args[0], "https://api.intasend.com/api/v1/checkout/")

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_live_example",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_intasend_authentication_uses_public_key_header_only_for_checkout(self, post):
        response = Mock()
        response.ok = True
        response.status_code = 201
        response.headers = {}
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://checkout.example/pay"}
        post.return_value = response
        PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
        )
        headers = post.call_args.kwargs["headers"]
        self.assertIn("X-IntaSend-Public-API-Key", headers)
        self.assertNotIn("Authorization", headers)

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_live_example",
        INTASEND_API_BASE_URL="https://sandbox.intasend.com",
    )
    def test_intasend_live_key_sandbox_endpoint_is_configuration_failure(self):
        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
        )
        self.assertEqual(result["url"], "")
        self.assertIn("live credentials", result["error"])

    @override_settings(
        INTASEND_PUBLIC_KEY="ISPubKey_test_example",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    def test_intasend_test_key_live_endpoint_is_configuration_failure(self):
        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
        )
        self.assertEqual(result["url"], "")
        self.assertIn("sandbox API URL", result["error"])
