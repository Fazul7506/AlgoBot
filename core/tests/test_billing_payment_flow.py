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


    @override_settings(
        PAYPAL_CLIENT_ID="sandbox-client", PAYPAL_CLIENT_SECRET="sandbox-secret",
        PAYPAL_MODE="sandbox", PAYPAL_API_BASE_URL="https://api-m.sandbox.paypal.com", PAYPAL_WEBHOOK_ID="WH-TEST", PAYPAL_BILLING_CURRENCY="USD",
    )
    @patch("core.services.payment_service.cache.set")
    @patch("core.services.payment_service.cache.get", return_value=None)
    @patch("core.services.payment_service.requests.post")
    def test_paypal_checkout_creates_server_priced_order_and_returns_approval_url(self, post, cache_get, cache_set):
        oauth = Mock(ok=True)
        oauth.json.return_value = {"access_token": "access-token", "expires_in": 3600}
        order = Mock(ok=True)
        order.json.return_value = {
            "id": "ORDER123456",
            "links": [{"rel": "payer-action", "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER123456"}],
        }
        post.side_effect = [oauth, order]
        reference = f"PY-{self.user.id}-BASIC-reference"
        result = PaymentService().create_paypal_checkout(
            self.user, CheckoutPlan(plan="BASIC", price_cents=99900, currency="USD", recurring=False, reference=reference, provider_request_id="checkout-ref-1"),
        )
        self.assertEqual(result["provider"], "paypal")
        self.assertEqual(result["order_id"], "ORDER123456")
        self.assertEqual(result["reference"], reference)
        self.assertTrue(result["url"].startswith("https://www.sandbox.paypal.com/"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["intent"], "CAPTURE")
        self.assertEqual(payload["purchase_units"][0]["amount"], {"currency_code": "USD", "value": "999.00"})
        self.assertEqual(payload["purchase_units"][0]["custom_id"], reference)
        self.assertEqual(post.call_args.kwargs["headers"]["PayPal-Request-Id"], "checkout-ref-1")

    @override_settings(
        PAYPAL_CLIENT_ID="sandbox-client", PAYPAL_CLIENT_SECRET="sandbox-secret",
        PAYPAL_MODE="sandbox", PAYPAL_API_BASE_URL="https://api-m.sandbox.paypal.com", PAYPAL_WEBHOOK_ID="WH-TEST", PAYPAL_BILLING_CURRENCY="USD",
    )
    @patch("core.services.payment_service.PaymentService.get_paypal_order")
    @patch("core.services.payment_service.PaymentService._paypal_access_token", return_value="access-token")
    @patch("core.services.payment_service.requests.post")
    def test_paypal_capture_activates_only_matching_completed_invoice(self, post, access_token, get_order):
        reference = f"PY-{self.user.id}-BASIC-capture"
        invoice = Invoice.objects.create(user=self.user, amount_cents=99900, currency="USD",
            external_id="ORDER123456", metadata={"plan": "BASIC", "provider": "paypal", "reference": reference})
        get_order.return_value = {"id": "ORDER123456", "status": "APPROVED", "purchase_units": [{
            "custom_id": reference, "amount": {"currency_code": "USD", "value": "999.00"},
        }]}
        captured = Mock(ok=True)
        captured.json.return_value = {"id": "ORDER123456", "status": "COMPLETED", "purchase_units": [{
            "custom_id": reference, "amount": {"currency_code": "USD", "value": "999.00"},
            "payments": {"captures": [{"id": "CAPTURE123", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "999.00"}}]},
        }]}
        post.return_value = captured
        result = PaymentService().capture_paypal_order("ORDER123456")
        invoice.refresh_from_db()
        self.assertTrue(result["paid"])
        self.assertTrue(invoice.paid)
        self.assertEqual(invoice.external_id, "ORDER123456")
        self.assertEqual(invoice.metadata["paypal_capture_id"], "CAPTURE123")
        self.assertEqual(invoice.metadata["paypal_order_id"], "ORDER123456")
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.provider, "paypal")
        self.assertFalse(subscription.recurring)


    @patch("core.services.payment_reconciler.PaymentService.get_paypal_order")
    def test_verified_paypal_capture_webhook_reconciles_matching_order_once(self, get_order):
        reference = f"PY-{self.user.id}-BASIC-webhook"
        invoice = Invoice.objects.create(user=self.user, amount_cents=99900, currency="USD",
            external_id="ORDERWEBHOOK", metadata={"plan": "BASIC", "provider": "paypal", "reference": reference, "paypal_order_id": "ORDERWEBHOOK"})
        get_order.return_value = {"id": "ORDERWEBHOOK", "status": "COMPLETED", "purchase_units": [{"custom_id": reference, "amount": {"currency_code": "USD", "value": "999.00"}}]}
        event = {"id": "WH-EVENT-1", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
            "id": "CAPTURE-WH-1", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "999.00"},
            "supplementary_data": {"related_ids": {"order_id": "ORDERWEBHOOK"}},
        }}
        result = PaymentReconciler.handle_paypal_webhook(event)
        invoice.refresh_from_db()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertTrue(invoice.paid)
        self.assertEqual(Payment.objects.get(external_id="CAPTURE-WH-1").status, "COMPLETED")
        duplicate = PaymentReconciler.handle_paypal_webhook(event)
        self.assertTrue(duplicate["duplicate"])

    @override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret", PAYPAL_WEBHOOK_ID="WH-TEST")
    @patch("core.services.payment_service.PaymentService._paypal_access_token", return_value="access-token")
    @patch("core.services.payment_service.requests.post")
    def test_paypal_webhook_verification_uses_paypal_verify_endpoint(self, post, access_token):
        response = Mock(ok=True)
        response.json.return_value = {"verification_status": "SUCCESS"}
        post.return_value = response
        headers = {"paypal-transmission-id": "tx-1", "paypal-transmission-time": "2026-11-06T10:00:00Z",
                   "paypal-cert-url": "https://api-m.sandbox.paypal.com/cert", "paypal-auth-algo": "SHA256withRSA",
                   "paypal-transmission-sig": "signature"}
        event = {"id": "event-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}
        self.assertTrue(PaymentService().verify_paypal_webhook(headers, event))
        self.assertEqual(post.call_args.args[0], "https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature")
        self.assertEqual(post.call_args.kwargs["json"]["webhook_id"], "WH-TEST")


    @override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret", PAYPAL_WEBHOOK_ID="WH-TEST")
    @patch("core.views_billing.PaymentService.get_paypal_order")
    def test_paypal_order_without_capture_amount_is_not_reported_as_paid(self, get_order):
        from core.views_billing import _reconcile_invoice
        reference = f"PY-{self.user.id}-BASIC-no-amount"
        invoice = Invoice.objects.create(user=self.user, amount_cents=99900, currency="USD", external_id="ORDERNOAMOUNT",
            metadata={"plan": "BASIC", "provider": "paypal", "reference": reference, "paypal_order_id": "ORDERNOAMOUNT"})
        get_order.return_value = {"id": "ORDERNOAMOUNT", "status": "COMPLETED", "purchase_units": [{
            "custom_id": reference, "amount": {"currency_code": "USD", "value": "999.00"},
            "payments": {"captures": [{"id": "CAPTURE-NO-AMOUNT", "status": "COMPLETED"}]},
        }]}
        result = _reconcile_invoice(invoice, "paypal")
        invoice.refresh_from_db()
        self.assertFalse(result["paid"])
        self.assertFalse(invoice.paid)
        self.assertEqual(result["state"], "CAPTURE_DETAILS_INCOMPLETE")

    @override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret", PAYPAL_WEBHOOK_ID="WH-TEST")
    @patch("core.views_billing.PaymentService.get_paypal_order")
    def test_paypal_success_response_cannot_mark_mismatched_invoice_paid(self, get_order):
        from core.views_billing import _reconcile_invoice
        reference = f"PY-{self.user.id}-BASIC-mismatch"
        invoice = Invoice.objects.create(user=self.user, amount_cents=99900, currency="USD", external_id="ORDERMISMATCH",
            metadata={"plan": "BASIC", "provider": "paypal", "reference": reference, "paypal_order_id": "ORDERMISMATCH"})
        get_order.return_value = {"id": "ORDERMISMATCH", "status": "COMPLETED", "purchase_units": [{
            "custom_id": reference, "amount": {"currency_code": "USD", "value": "999.00"},
            "payments": {"captures": [{"id": "CAPTURE-MISMATCH", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "1.00"}}]},
        }]}
        result = _reconcile_invoice(invoice, "paypal")
        invoice.refresh_from_db()
        self.assertFalse(result["paid"])
        self.assertFalse(invoice.paid)
        self.assertEqual(result["reconciled"]["rejected"], "amount_mismatch")

    @override_settings(
        ALGOBOT_BILLING_CURRENCY="KES", ALGOBOT_BASIC_PRICE_CENTS=250000,
        PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret", PAYPAL_WEBHOOK_ID="WH-TEST",
        PAYPAL_MODE="sandbox", PAYPAL_BILLING_CURRENCY="USD", PAYPAL_BASIC_PRICE_CENTS=1999,
    )
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session", return_value={"url": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER123", "session_id": "ORDER123", "reference": "PY-1-BASIC-ref"})
    def test_paypal_checkout_uses_explicit_usd_price_without_converting_kes_catalogue(self, create_checkout):
        from django.test import RequestFactory
        from core.views_billing import _checkout
        request = RequestFactory().post("/billing/checkout/start/")
        request.user = self.user
        url, error = _checkout(request, "BASIC", "paypal")
        self.assertIsNone(error)
        self.assertTrue(url.startswith("https://www.sandbox.paypal.com/"))
        invoice = Invoice.objects.get(user=self.user, metadata__provider="paypal")
        self.assertEqual((invoice.amount_cents, invoice.currency), (1999, "USD"))
        checkout_plan = create_checkout.call_args.args[1]
        self.assertEqual((checkout_plan.price_cents, checkout_plan.currency), (1999, "USD"))
        self.assertFalse(checkout_plan.recurring)

    @override_settings(
        PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret", PAYPAL_WEBHOOK_ID="WH-TEST",
        PAYPAL_MODE="sandbox", PAYPAL_BILLING_CURRENCY="KES",
    )
    def test_paypal_checkout_rejects_unsupported_kes_currency(self):
        result = PaymentService().create_paypal_checkout(
            self.user, CheckoutPlan(plan="BASIC", price_cents=99900, currency="KES", recurring=False),
        )
        self.assertEqual(result["url"], "")
        self.assertIn("does not support KES", result["error"])


    @override_settings(
        PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret", PAYPAL_WEBHOOK_ID="WH-TEST",
        PAYPAL_MODE="sandbox", PAYPAL_API_BASE_URL="https://attacker.example",
    )
    @patch("core.services.payment_service.requests.post")
    def test_paypal_rejects_untrusted_api_host_before_sending_credentials(self, post):
        service = PaymentService()
        self.assertFalse(service.paypal_is_configured())
        self.assertIsNone(service._paypal_access_token())
        post.assert_not_called()

    @override_settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="")
    def test_paypal_checkout_fails_closed_without_credentials(self):
        result = PaymentService().create_paypal_checkout(
            self.user, CheckoutPlan(plan="BASIC", price_cents=99900, currency="USD", recurring=False),
        )
        self.assertEqual(result["url"], "")
        self.assertIn("PAYPAL_CLIENT_ID", result["error"])

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
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://sandbox.intasend.com/checkout/test-session"}
        post.return_value = response

        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=99900, currency="USD", recurring=False),
        )

        self.assertEqual(result["url"], "https://sandbox.intasend.com/checkout/test-session")
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
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://sandbox.intasend.com/checkout/test-session"}
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
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://sandbox.intasend.com/checkout/test-session"}
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
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://sandbox.intasend.com/checkout/test-session"}
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
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://payment.intasend.com/checkout/test-session"}
        post.return_value = response

        result = PaymentService().create_intasend_checkout(
            self.user,
            CheckoutPlan(plan="BASIC", price_cents=50000, currency="KES", recurring=False),
        )
        self.assertEqual(result["url"], "https://payment.intasend.com/checkout/test-session")
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
        response.json.return_value = {"invoice_id": "IS-INVOICE", "url": "https://payment.intasend.com/checkout/test-session"}
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