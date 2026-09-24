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

    @override_settings(ALGOBOT_PRO_PRICE_CENTS="0")
    def test_zero_price_paid_plan_is_not_sent_to_a_provider(self):
        response = self.client.post(reverse("billing_checkout"), {"plan": "PRO"}, format="json", **self.api_headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"])

    @override_settings(BILLING_SUCCESS_URL="https://algobot.dpdns.org/billing/success/", BILLING_CANCEL_URL="https://algobot.dpdns.org/billing/cancel/", PESAPAL_CALLBACK_URL="https://algobot.dpdns.org/payments/pesapal/callback/")
    def test_explicit_provider_callback_urls_are_used(self):
        service = PaymentService()
        self.assertEqual(service._callback_url("BILLING_SUCCESS_URL", "/billing/success/", {"provider": "intasend", "reference": "IS-1-BASIC-X"}), "https://algobot.dpdns.org/billing/success/?provider=intasend&reference=IS-1-BASIC-X")
        self.assertEqual(service._callback_url("BILLING_CANCEL_URL", "/billing/cancel/"), "https://algobot.dpdns.org/billing/cancel/")
        self.assertEqual(service._callback_url("PESAPAL_CALLBACK_URL", "/payments/pesapal/callback/"), "https://algobot.dpdns.org/payments/pesapal/callback/")

    @override_settings(ALGOBOT_BASIC_PRICE_CENTS="50000", ALGOBOT_BILLING_CURRENCY="KES")
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session")
    def test_authenticated_checkout_start_works_with_django_simple_lazy_object(self, create_checkout):
        create_checkout.return_value = {
            "url": "https://checkout.example/pay",
            "invoice_id": "IS-SIMPLE-LAZY-1",
            "reference": "IS-SIMPLE-LAZY-REF",
        }
        response = self.client.post(reverse("billing_checkout_start"), {"plan": "BASIC", "provider": "intasend"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.example/pay")
        invoice = Invoice.objects.get(user=self.user, metadata__plan="BASIC")
        self.assertEqual(invoice.external_id, "IS-SIMPLE-LAZY-1")
        self.assertEqual(invoice.metadata["state"], "checkout_open")
        create_checkout.assert_called_once()

    @override_settings(ALGOBOT_BASIC_PRICE_CENTS="50000", ALGOBOT_BILLING_CURRENCY="KES")
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session")
    def test_failed_checkout_does_not_activate_subscription(self, create_checkout):
        create_checkout.return_value = {
            "url": "",
            "error": "IntaSend is temporarily unavailable. Please try again.",
            "error_classification": "provider unavailable",
        }
        response = self.client.post(reverse("billing_checkout_start"), {"plan": "BASIC", "provider": "intasend"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("billing_page"))
        invoice = Invoice.objects.get(user=self.user)
        self.assertFalse(invoice.paid)
        self.assertEqual(invoice.metadata["state"], "checkout_failed")
        self.assertEqual(invoice.metadata["error_classification"], "provider unavailable")
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())
        self.assertEqual(Subscription.objects.get(user=self.user).plan, "FREE")

    @override_settings(ALGOBOT_BASIC_PRICE_CENTS="50000", ALGOBOT_BILLING_CURRENCY="KES")
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session")
    def test_retry_reuses_failed_invoice_instead_of_creating_duplicates(self, create_checkout):
        create_checkout.side_effect = [
            {"url": "", "error": "provider failure", "error_classification": "provider unavailable"},
            {"url": "https://checkout.example/pay", "invoice_id": "IS-RETRY-1", "reference": "IS-RETRY-REF"},
        ]
        first = self.client.post(reverse("billing_checkout_start"), {"plan": "BASIC", "provider": "intasend"})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(Invoice.objects.filter(user=self.user, metadata__plan="BASIC").count(), 1)

        second = self.client.post(reverse("billing_checkout_start"), {"plan": "BASIC", "provider": "intasend"})
        self.assertEqual(second.status_code, 302)
        self.assertEqual(second.url, "https://checkout.example/pay")
        self.assertEqual(Invoice.objects.filter(user=self.user, metadata__plan="BASIC").count(), 1)
        invoice = Invoice.objects.get(user=self.user, metadata__plan="BASIC")
        self.assertEqual(invoice.external_id, "IS-RETRY-1")
        self.assertEqual(invoice.metadata["state"], "checkout_open")
        self.assertEqual(create_checkout.call_count, 2)


    def test_completed_payment_cannot_regress_to_pending_or_failed(self):
        metadata = {"api_ref": f"IS-{self.user.id}-BASIC-MONO", "user_id": self.user.id, "plan": "BASIC"}
        first = PaymentReconciler.reconcile(provider="intasend", external_id="MONO-1", status="COMPLETE", amount="999.00", currency="KES", metadata=metadata)
        self.assertEqual(first["status"], "COMPLETED")
        stale = PaymentReconciler.reconcile(provider="intasend", external_id="MONO-1", status="FAILED", amount="999.00", currency="KES", metadata=metadata)
        self.assertEqual(stale["status"], "COMPLETED")
        self.assertEqual(Payment.objects.get(external_id="MONO-1").status, "COMPLETED")
        self.assertTrue(Invoice.objects.get(external_id="MONO-1").paid)

    def test_currency_mismatch_is_rejected(self):
        reference = f"IS-{self.user.id}-BASIC-CURRENCY"
        invoice = Invoice.objects.create(user=self.user, amount_cents=99900, currency="KES", metadata={"plan": "BASIC", "provider": "intasend", "reference": reference})
        result = PaymentReconciler.reconcile(
            provider="intasend",
            external_id="CURRENCY-1",
            status="COMPLETE",
            amount="999.00",
            currency="USD",
            metadata={"api_ref": reference, "plan": "BASIC", "user_id": self.user.id},
        )
        self.assertEqual(result["rejected"], "currency_mismatch")
        invoice.refresh_from_db()
        self.assertFalse(invoice.paid)

    @override_settings(INTASEND_WEBHOOK_CHALLENGE="expected")
    @patch("core.services.payment_reconciler.PaymentService.get_intasend_payment_status")
    def test_intasend_webhook_requires_configured_challenge(self, get_status):
        payload = {"invoice_id": "WEBHOOK-AUTH", "state": "COMPLETE", "challenge": "wrong"}
        self.assertIsNone(PaymentReconciler.handle_intasend_webhook(payload))
        get_status.assert_not_called()

    @override_settings(INTASEND_WEBHOOK_CHALLENGE="expected")
    @patch("core.services.payment_reconciler.PaymentService.get_intasend_payment_status")
    def test_intasend_webhook_uses_provider_status_not_client_state(self, get_status):
        reference = f"IS-{self.user.id}-BASIC-AUTH"
        Invoice.objects.create(user=self.user, amount_cents=99900, currency="KES", metadata={"plan": "BASIC", "provider": "intasend", "reference": reference})
        get_status.return_value = {"invoice": {"invoice_id": "WEBHOOK-AUTH", "state": "PENDING", "value": "999.00", "currency": "KES"}}
        result = PaymentReconciler.handle_intasend_webhook({"invoice_id": "WEBHOOK-AUTH", "state": "COMPLETE", "value": "999.00", "currency": "KES", "api_ref": reference, "challenge": "expected"})
        self.assertEqual(result["status"], "PENDING")
        self.assertFalse(Invoice.objects.get(metadata__reference=reference).paid)



    @override_settings(ALGOBOT_BASIC_PRICE_CENTS="50000", ALGOBOT_BILLING_CURRENCY="KES")
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session")
    @patch("core.views_billing.PaymentService.get_intasend_payment_status")
    def test_failed_open_checkout_is_reconciled_and_can_be_restarted(self, get_status, create_checkout):
        invoice = Invoice.objects.create(
            user=self.user,
            amount_cents=50000,
            currency="KES",
            metadata={"plan": "BASIC", "provider": "intasend", "state": "checkout_open", "reference": "IS-RETRY-OLD"},
            external_id="IS-OLD-FAILED",
        )
        get_status.return_value = {
            "invoice": {
                "invoice_id": "IS-OLD-FAILED",
                "state": "FAILED",
                "value": "500.00",
                "currency": "KES",
            }
        }
        create_checkout.return_value = {
            "url": "https://checkout.example/new",
            "invoice_id": "IS-NEW-1",
            "reference": "IS-NEW-REF",
        }

        response = self.client.post(
            reverse("billing_checkout_start"),
            {"plan": "BASIC", "provider": "intasend"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.example/new")
        invoice.refresh_from_db()
        self.assertEqual(invoice.external_id, "IS-NEW-1")
        self.assertEqual(invoice.metadata["state"], "checkout_open")
        self.assertEqual(invoice.metadata["reference"], "IS-NEW-REF")
        create_checkout.assert_called_once()

    @override_settings(ALGOBOT_BASIC_PRICE_CENTS="50000", ALGOBOT_BILLING_CURRENCY="KES")
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session")
    @patch("core.views_billing.PaymentService.get_intasend_payment_status")
    def test_pending_open_checkout_stays_blocked(self, get_status, create_checkout):
        Invoice.objects.create(
            user=self.user,
            amount_cents=50000,
            currency="KES",
            metadata={"plan": "BASIC", "provider": "intasend", "state": "checkout_open", "reference": "IS-PENDING"},
            external_id="IS-PENDING-1",
        )
        get_status.return_value = {
            "invoice": {
                "invoice_id": "IS-PENDING-1",
                "state": "PENDING",
                "value": "500.00",
                "currency": "KES",
            }
        }

        response = self.client.post(
            reverse("billing_checkout_start"),
            {"plan": "BASIC", "provider": "intasend"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("billing_page"))
        create_checkout.assert_not_called()
        invoice = Invoice.objects.get(user=self.user, external_id="IS-PENDING-1")
        self.assertEqual(invoice.metadata["state"], "checkout_open")


class BillingCheckoutSecretPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="billing-secret", password="pass12345")
        self.client.login(username="billing-secret", password="pass12345")

    @override_settings(ALGOBOT_BASIC_PRICE_CENTS="50000", ALGOBOT_BILLING_CURRENCY="KES")
    @patch("core.views_billing.RequestBoundPaymentService.create_checkout_session")
    def test_hosted_checkout_url_is_returned_but_never_persisted(self, create_checkout):
        create_checkout.return_value = {
            "url": "https://payment.intasend.com/subscriptions/charge/redacted",
            "invoice_id": "SUB-SECRET-1",
            "session_id": "SUB-SECRET-1",
            "subscription_id": "SUB-SECRET-1",
            "reference": "IS-SECRET-REF",
        }
        response = self.client.post(reverse("billing_checkout_start"), {"plan": "BASIC", "provider": "intasend"})
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get(user=self.user)
        self.assertNotIn("checkout_url", invoice.metadata)
        status_response = self.client.get(reverse("billing_status"))
        body = status_response.json()
        self.assertNotIn("checkout_url", str(body))

    def test_provider_payload_sanitizer_redacts_setup_urls_and_tokens(self):
        safe = PaymentReconciler._sanitize_provider_payload({
            "setup_url": "https://payment.intasend.com/subscriptions/charge/redacted",
            "token": "secret-token",
            "nested": {"checkout_url": "https://payment.intasend.com/subscriptions/charge/redacted"},
            "subscription_id": "SUB-1",
        })
        self.assertEqual(safe["setup_url"], "[REDACTED]")
        self.assertEqual(safe["token"], "[REDACTED]")
        self.assertEqual(safe["nested"]["checkout_url"], "[REDACTED]")
        self.assertEqual(safe["subscription_id"], "SUB-1")
