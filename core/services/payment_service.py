"""Provider-neutral payment integration for IntaSend and Pesapal."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class PaymentService:
    """Create provider checkouts and perform provider status lookups.

    Payment persistence, subscription activation, and referral accounting are
    intentionally delegated to :class:`PaymentReconciler` so there is one
    canonical state machine for provider callbacks.
    """

    INTASEND = "intasend"
    PESAPAL = "pesapal"

    def __init__(self):
        self.provider = str(getattr(settings, "PAYMENT_PROVIDER", self.INTASEND)).lower().strip()
        self.intasend_public_key = getattr(settings, "INTASEND_PUBLIC_KEY", "")
        self.intasend_secret_key = getattr(settings, "INTASEND_SECRET_KEY", "")
        self.intasend_webhook_challenge = getattr(settings, "INTASEND_WEBHOOK_CHALLENGE", "")
        self.intasend_base_url = str(getattr(settings, "INTASEND_API_BASE_URL", "https://api.intasend.com") or "https://api.intasend.com").strip().rstrip("/")
        self.intasend_mobile_tariff = str(getattr(settings, "INTASEND_MOBILE_TARIFF", "") or "").strip()
        self.intasend_card_tariff = str(getattr(settings, "INTASEND_CARD_TARIFF", "") or "").strip()
        self.pesapal_consumer_key = getattr(settings, "PESAPAL_CONSUMER_KEY", "")
        self.pesapal_consumer_secret = getattr(settings, "PESAPAL_CONSUMER_SECRET", "")
        self.pesapal_notification_id = getattr(settings, "PESAPAL_NOTIFICATION_ID", "")
        self.pesapal_base_url = getattr(settings, "PESAPAL_API_BASE_URL", "https://pay.pesapal.com/v3").rstrip("/")
        # A malformed deployment value must not make every checkout fail
        # before a request reaches the selected provider.
        self.timeout = self._request_timeout(getattr(settings, "PAYMENT_HTTP_TIMEOUT", 20))

    def create_checkout_session(self, user, subscription_plan, provider: str | None = None):
        selected = str(provider or self.provider).lower().strip()
        logger.info("Creating %s checkout for %s plan=%s", selected, getattr(user, "username", None), subscription_plan)
        if selected == self.INTASEND:
            return self.create_intasend_checkout(user, subscription_plan)
        if selected == self.PESAPAL:
            return self.create_pesapal_checkout(user, subscription_plan)
        return {"url": "", "provider": selected, "error": "Unsupported payment provider"}

    def create_intasend_checkout(self, user, subscription_plan):
        if bool(getattr(subscription_plan, "recurring", False)):
            return self.create_intasend_subscription(user, subscription_plan)

        if not self.intasend_public_key:
            return self._configuration_error("INTASEND_PUBLIC_KEY")
        environment_error = self._intasend_environment_error()
        if environment_error:
            logger.error("IntaSend environment configuration mismatch: %s", environment_error)
            return {"url": "", "provider": self.INTASEND, "error": environment_error}
        amount, currency = self._amount_and_currency(subscription_plan)
        # The billing view creates an internal reference before it persists the
        # invoice.  Reusing it here is essential: IntaSend returns this value
        # in its webhook/redirect payload, and generating another value would
        # leave a successful payment unable to be matched to that invoice.
        api_ref = str(getattr(subscription_plan, "reference", "") or "").strip()
        if not api_ref:
            api_ref = self._reference("IS", user, subscription_plan)
        # IntaSend's redirect_url validator rejects '&' in query strings.
        # Keep the callback to one safe query parameter and infer the provider
        # from the IS- reference prefix on the success page.
        redirect_url = self._callback_url(
            "BILLING_SUCCESS_URL",
            "/billing/success/",
            {"reference": api_ref},
        )
        host_url = self._base_url()
        payload = {
            "amount": self._decimal_string(amount),
            "currency": currency.upper(),
            "api_ref": api_ref,
            "email": getattr(user, "email", "") or None,
            "first_name": getattr(user, "first_name", "") or None,
            "last_name": getattr(user, "last_name", "") or None,
            "country": "KE" if currency.upper() == "KES" else None,
            "channel": "WEBSITE",
            "host": host_url,
            "redirect_url": redirect_url,
            # Tariffs are merchant-specific.  Do not force BUSINESS-PAYS (or
            # any other value) because unprovisioned tariffs cause IntaSend to
            # reject the entire checkout request.
            "mobile_tarrif": self.intasend_mobile_tariff or None,
            "card_tarrif": self.intasend_card_tariff or None,
        }
        self._drop_none(payload)
        try:
            response = requests.post(
                f"{self.intasend_base_url}/api/v1/checkout/",
                json=payload,
                headers={
                    "X-IntaSend-Public-API-Key": self.intasend_public_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
            data = self._json_or_error(response)
            request_id = self._provider_request_id(response)
            if not response.ok:
                classification = self._classify_provider_failure(response.status_code, data)
                self._log_provider_diagnostic(
                    provider=self.INTASEND,
                    endpoint=self._endpoint_for_log(self.intasend_base_url, "/api/v1/checkout/"),
                    method="POST",
                    status_code=response.status_code,
                    request_id=request_id,
                    merchant_reference=api_ref,
                    plan=getattr(subscription_plan, "plan", ""),
                    currency=currency,
                    amount=amount,
                    recurring=bool(getattr(subscription_plan, "recurring", False)),
                    payload=payload,
                    response=data,
                    classification=classification,
                )
                return {"url": "", "provider": self.INTASEND, "error": self._checkout_http_error(self.INTASEND, response.status_code, data), "error_classification": classification}
            url = data.get("url") or data.get("checkout_url") or data.get("link") or ""
            invoice_id = data.get("invoice_id") or data.get("id") or data.get("checkout_id")
            if not self._is_checkout_url(url):
                logger.error("IntaSend checkout returned success without a checkout URL: %s", data)
                return {"url": "", "provider": self.INTASEND, "error": "Payment provider returned no checkout URL"}
            self._log_provider_diagnostic(
                provider=self.INTASEND,
                endpoint=self._endpoint_for_log(self.intasend_base_url, "/api/v1/checkout/"),
                method="POST",
                status_code=response.status_code,
                request_id=request_id,
                merchant_reference=api_ref,
                plan=getattr(subscription_plan, "plan", ""),
                currency=currency,
                amount=amount,
                recurring=bool(getattr(subscription_plan, "recurring", False)),
                payload=payload,
                response={"checkout_url_present": True, "invoice_id_present": bool(invoice_id)},
                classification="success",
            )
            return {
                "provider": self.INTASEND,
                "session_id": invoice_id or api_ref,
                "invoice_id": invoice_id,
                "reference": api_ref,
                "url": url,
            }
        except requests.Timeout as exc:
            self._log_provider_diagnostic(
                provider=self.INTASEND,
                endpoint=self._endpoint_for_log(self.intasend_base_url, "/api/v1/checkout/"),
                method="POST",
                status_code=None,
                request_id=None,
                merchant_reference=api_ref,
                plan=getattr(subscription_plan, "plan", ""),
                currency=currency,
                amount=amount,
                recurring=bool(getattr(subscription_plan, "recurring", False)),
                payload=payload,
                response=None,
                classification="timeout/network failure",
                exception=exc,
            )
            return {"url": "", "provider": self.INTASEND, "error": "Payment provider is temporarily unavailable. Please try again.", "error_classification": "timeout/network failure"}
        except requests.RequestException as exc:
            self._log_provider_diagnostic(
                provider=self.INTASEND,
                endpoint=self._endpoint_for_log(self.intasend_base_url, "/api/v1/checkout/"),
                method="POST",
                status_code=None,
                request_id=None,
                merchant_reference=api_ref,
                plan=getattr(subscription_plan, "plan", ""),
                currency=currency,
                amount=amount,
                recurring=bool(getattr(subscription_plan, "recurring", False)),
                payload=payload,
                response=None,
                classification="timeout/network failure",
                exception=exc,
            )
            return {"url": "", "provider": self.INTASEND, "error": "Payment provider is temporarily unavailable. Please try again.", "error_classification": "timeout/network failure"}

    def create_intasend_subscription(self, user, subscription_plan):
        """Create a real IntaSend recurring subscription and return its setup URL."""
        if not self.intasend_secret_key:
            return self._configuration_error("INTASEND_SECRET_KEY")
        if not self.intasend_public_key:
            return self._configuration_error("INTASEND_PUBLIC_KEY")
        environment_error = self._intasend_environment_error()
        if environment_error:
            return {"url": "", "provider": self.INTASEND, "error": environment_error, "error_classification": "configuration/authentication failure"}

        amount, currency = self._amount_and_currency(subscription_plan)
        reference = str(getattr(subscription_plan, "reference", "") or self._reference("IS", user, subscription_plan)).strip()
        headers = {
            "Authorization": f"Bearer {self.intasend_secret_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        base = self.intasend_base_url
        customer_payload = {
            "email": getattr(user, "email", "") or "",
            "first_name": getattr(user, "first_name", "") or getattr(user, "username", "Customer"),
            # IntaSend validates last_name as non-blank for recurring customers.
            # A user may legitimately have no surname in Django, so use a
            # provider-safe neutral fallback rather than sending an empty field.
            "last_name": getattr(user, "last_name", "") or "Customer",
            "reference": f"{reference}-CUSTOMER",
            "country": "KE" if currency.upper() == "KES" else "",
        }
        plan_name = f"AlgoBot-{str(getattr(subscription_plan, 'plan', 'PLAN')).upper()}"[:32]
        plan_payload = {
            "name": plan_name,
            "frequency": 1,
            "frequency_unit": "M",
            "billing_cycles": 0,
            "currency": currency.upper(),
            "amount": self._decimal_string(amount),
            "reference": reference,
            "redirect_url": self._callback_url("BILLING_SUCCESS_URL", "/billing/success/", {"reference": reference}),
        }
        try:
            customer_response = requests.post(
                f"{base}/api/v1/subscriptions-customers/",
                json=customer_payload, headers=headers, timeout=self.timeout,
            )
            customer_data = self._json_or_error(customer_response)
            if not customer_response.ok:
                self._log_provider_diagnostic(
                    provider=self.INTASEND, endpoint=self._endpoint_for_log(base, "/api/v1/subscriptions-customers/"),
                    method="POST", status_code=customer_response.status_code,
                    request_id=self._provider_request_id(customer_response), merchant_reference=reference,
                    plan=getattr(subscription_plan, "plan", ""), currency=currency, amount=amount,
                    recurring=True, payload=customer_payload, response=customer_data,
                    classification=self._classify_provider_failure(customer_response.status_code, customer_data),
                )
                return {"url": "", "provider": self.INTASEND, "error": self._checkout_http_error(self.INTASEND, customer_response.status_code, customer_data), "error_classification": self._classify_provider_failure(customer_response.status_code, customer_data)}

            customer_id = customer_data.get("customer_id") or customer_data.get("id")
            if not customer_id:
                return {"url": "", "provider": self.INTASEND, "error": "IntaSend returned no subscription customer ID.", "error_classification": "malformed provider response"}

            plan_response = requests.post(
                f"{base}/api/v1/subscriptions-plans/",
                json=plan_payload, headers=headers, timeout=self.timeout,
            )
            plan_data = self._json_or_error(plan_response)
            if not plan_response.ok:
                self._log_provider_diagnostic(
                    provider=self.INTASEND, endpoint=self._endpoint_for_log(base, "/api/v1/subscriptions-plans/"),
                    method="POST", status_code=plan_response.status_code,
                    request_id=self._provider_request_id(plan_response), merchant_reference=reference,
                    plan=getattr(subscription_plan, "plan", ""), currency=currency, amount=amount,
                    recurring=True, payload=plan_payload, response=plan_data,
                    classification=self._classify_provider_failure(plan_response.status_code, plan_data),
                )
                return {"url": "", "provider": self.INTASEND, "error": self._checkout_http_error(self.INTASEND, plan_response.status_code, plan_data), "error_classification": self._classify_provider_failure(plan_response.status_code, plan_data)}

            plan_id = plan_data.get("plan_id") or plan_data.get("id")
            if not plan_id:
                return {"url": "", "provider": self.INTASEND, "error": "IntaSend returned no subscription plan ID.", "error_classification": "malformed provider response"}

            subscribe_payload = {
                "customer_id": customer_id,
                "plan_id": plan_id,
                "reference": reference,
                "start_date": datetime.now(dt_timezone.utc).date().isoformat(),
                "redirect_url": self._callback_url("BILLING_SUCCESS_URL", "/billing/success/", {"reference": reference}),
            }
            subscribe_response = requests.post(
                f"{base}/api/v1/subscriptions/",
                json=subscribe_payload, headers=headers, timeout=self.timeout,
            )
            subscribe_data = self._json_or_error(subscribe_response)
            request_id = self._provider_request_id(subscribe_response)
            if not subscribe_response.ok:
                classification = self._classify_provider_failure(subscribe_response.status_code, subscribe_data)
                self._log_provider_diagnostic(
                    provider=self.INTASEND, endpoint=self._endpoint_for_log(base, "/api/v1/subscriptions/"),
                    method="POST", status_code=subscribe_response.status_code, request_id=request_id,
                    merchant_reference=reference, plan=getattr(subscription_plan, "plan", ""),
                    currency=currency, amount=amount, recurring=True, payload=subscribe_payload,
                    response=subscribe_data, classification=classification,
                )
                return {"url": "", "provider": self.INTASEND, "error": self._checkout_http_error(self.INTASEND, subscribe_response.status_code, subscribe_data), "error_classification": classification}

            setup_url = subscribe_data.get("setup_url") or subscribe_data.get("url")
            subscription_id = subscribe_data.get("subscription_id") or subscribe_data.get("id")
            if not self._is_checkout_url(setup_url) or not subscription_id:
                return {"url": "", "provider": self.INTASEND, "error": "IntaSend returned incomplete subscription checkout data.", "error_classification": "malformed provider response"}

            self._log_provider_diagnostic(
                provider=self.INTASEND, endpoint=self._endpoint_for_log(base, "/api/v1/subscriptions/"),
                method="POST", status_code=subscribe_response.status_code, request_id=request_id,
                merchant_reference=reference, plan=getattr(subscription_plan, "plan", ""),
                currency=currency, amount=amount, recurring=True,
                payload=subscribe_payload,
                response={"setup_url_present": True, "subscription_id_present": True},
                classification="success",
            )
            return {
                "provider": self.INTASEND, "session_id": subscription_id,
                "invoice_id": subscription_id, "reference": reference, "url": setup_url,
                "subscription_id": subscription_id, "provider_plan_id": plan_id, "provider_customer_id": customer_id,
            }
        except requests.RequestException as exc:
            self._log_provider_diagnostic(
                provider=self.INTASEND, endpoint=self._endpoint_for_log(base, "/api/v1/subscriptions/"),
                method="POST", status_code=None, request_id=None, merchant_reference=reference,
                plan=getattr(subscription_plan, "plan", ""), currency=currency, amount=amount,
                recurring=True, payload={"reference": reference}, response=None,
                classification="timeout/network failure", exception=exc,
            )
            return {"url": "", "provider": self.INTASEND, "error": "Payment provider is temporarily unavailable. Please try again.", "error_classification": "timeout/network failure"}

    def create_pesapal_checkout(self, user, subscription_plan):
        if not self.pesapal_consumer_key:
            return self._configuration_error("PESAPAL_CONSUMER_KEY")
        if not self.pesapal_consumer_secret:
            return self._configuration_error("PESAPAL_CONSUMER_SECRET")
        if not self.pesapal_notification_id:
            return self._configuration_error("PESAPAL_NOTIFICATION_ID")
        amount, currency = self._amount_and_currency(subscription_plan)
        reference = self._reference("PP", user, subscription_plan)
        callback_url = self._callback_url("PESAPAL_CALLBACK_URL", "/payments/pesapal/callback/")
        cancellation_url = self._callback_url("PESAPAL_CANCELLATION_URL", "/billing/cancel/")
        token = self._pesapal_access_token()
        if not token:
            return {"url": "", "provider": self.PESAPAL, "error": "Unable to authenticate with Pesapal"}
        billing_address = {
            "email_address": getattr(user, "email", "") or "",
            "phone_number": getattr(getattr(user, "trading_profile", None), "phone", "") or "",
            "country_code": "KE" if currency.upper() == "KES" else "",
            "first_name": getattr(user, "first_name", "") or getattr(user, "username", "Customer"),
            "middle_name": "",
            "last_name": getattr(user, "last_name", "") or "",
            "line_1": "",
            "line_2": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "zip_code": "",
        }
        payload = {
            "id": reference,
            "currency": currency.upper(),
            "amount": self._decimal_string(amount),
            "description": f"AlgoBot {getattr(subscription_plan, 'plan', subscription_plan)} subscription",
            "callback_url": callback_url,
            "cancellation_url": cancellation_url,
            "notification_id": self.pesapal_notification_id,
            "billing_address": billing_address,
        }
        if getattr(subscription_plan, "recurring", False):
            payload["account_number"] = f"ALGOBOT-{user.id}"
        try:
            response = requests.post(
                f"{self.pesapal_base_url}/api/Transactions/SubmitOrderRequest",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            data = self._json_or_error(response)
            if not response.ok:
                logger.error("Pesapal order failed status=%s body=%s", response.status_code, data)
                return {"url": "", "provider": self.PESAPAL, "error": self._checkout_http_error(self.PESAPAL, response.status_code, data)}
            url = data.get("redirect_url") or data.get("url") or ""
            tracking_id = data.get("order_tracking_id") or data.get("tracking_id")
            if not self._is_checkout_url(url) or not tracking_id:
                logger.error("Pesapal checkout returned incomplete order data: %s", data)
                return {"url": "", "provider": self.PESAPAL, "error": "Payment provider returned incomplete checkout data"}
            return {
                "provider": self.PESAPAL,
                "session_id": tracking_id,
                "order_tracking_id": tracking_id,
                "reference": reference,
                "url": url,
            }
        except requests.RequestException as exc:
            logger.exception("Pesapal checkout request failed")
            return {"url": "", "provider": self.PESAPAL, "error": "Payment provider is temporarily unreachable. Please try again."}

    def handle_webhook(self, payload: bytes | dict, sig_header: str = "", provider: str | None = None) -> Optional[dict]:
        """Compatibility entry point that delegates to the canonical reconciler."""
        from core.services.payment_reconciler import PaymentReconciler
        selected = str(provider or self.provider).lower().strip()
        if selected == self.INTASEND:
            return PaymentReconciler.handle_intasend_webhook(payload)
        if selected == self.PESAPAL:
            return PaymentReconciler.handle_pesapal_webhook(payload)
        logger.warning("Received webhook for unsupported provider %s", selected)
        return None

    def handle_pesapal_callback(self, order_tracking_id: str, merchant_reference: str = ""):
        """Compatibility entry point that delegates to the canonical reconciler."""
        from core.services.payment_reconciler import PaymentReconciler
        return PaymentReconciler.handle_pesapal_callback(order_tracking_id, merchant_reference)

    def get_pesapal_transaction_status(self, order_tracking_id: str) -> Optional[dict]:
        token = self._pesapal_access_token()
        if not token or not order_tracking_id:
            return None
        try:
            response = requests.get(
                f"{self.pesapal_base_url}/api/Transactions/GetTransactionStatus",
                params={"orderTrackingId": order_tracking_id},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=self.timeout,
            )
            data = self._json_or_error(response)
            if not response.ok:
                logger.error("Pesapal status request failed: %s", data)
                return None
            return data
        except requests.RequestException:
            logger.exception("Pesapal status request failed")
            return None

    def get_intasend_payment_status(self, invoice_id: str) -> Optional[dict]:
        if not self.intasend_secret_key or not invoice_id:
            return None
        try:
            response = requests.post(
                f"{self.intasend_base_url}/api/v1/payment/status/",
                json={"invoice_id": invoice_id},
                headers={
                    "Authorization": f"Bearer {self.intasend_secret_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
            data = self._json_or_error(response)
            if not response.ok:
                logger.error("IntaSend status request failed: %s", data)
                return None
            return data
        except requests.RequestException:
            logger.exception("IntaSend status request failed")
            return None

    def create_invoice_record(self, user, amount_cents: int, currency: str = "KES"):
        from core.models import Invoice
        return Invoice.objects.create(user=user, amount_cents=amount_cents, currency=currency)

    def _pesapal_access_token(self) -> Optional[str]:
        cache_key = "algobot:pesapal:access_token"
        try:
            cached = cache.get(cache_key)
            if cached:
                return str(cached)
        except Exception:
            logger.warning("Pesapal token cache unavailable; requesting a fresh token")
        try:
            response = requests.post(
                f"{self.pesapal_base_url}/api/Auth/RequestToken",
                json={"consumer_key": self.pesapal_consumer_key, "consumer_secret": self.pesapal_consumer_secret},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            data = self._json_or_error(response)
            if not response.ok:
                logger.error("Pesapal authentication failed: %s", data)
                return None
            token = data.get("token")
            if token:
                try:
                    cache.set(cache_key, token, timeout=240)
                except Exception:
                    pass
            return token
        except requests.RequestException:
            logger.exception("Pesapal authentication request failed")
            return None

    def _amount_and_currency(self, subscription_plan):
        raw_amount = getattr(subscription_plan, "price_cents", 0) if not isinstance(subscription_plan, str) else 0
        currency = getattr(subscription_plan, "currency", "KES") if not isinstance(subscription_plan, str) else "KES"
        try:
            amount = Decimal(str(raw_amount or 0)) / Decimal("100")
        except (InvalidOperation, ValueError):
            amount = Decimal("0")
        return amount, str(currency or "KES")

    def _base_url(self):
        raw = str(getattr(settings, "BASE_URL", "") or "").strip().strip('"').strip("'")
        base = raw.split(",", 1)[0].strip().rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(ch.isspace() for ch in base):
            logger.error("Invalid BASE_URL for payment callbacks; using production canonical URL")
            return "https://algobot.dpdns.org"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}" or "https://algobot.dpdns.org"

    def _callback_url(self, setting_name, default_path, params=None):
        configured = str(getattr(settings, setting_name, "") or "").strip().strip('"').strip("'")
        if configured:
            parsed = urlsplit(configured)
            if parsed.scheme in {"http", "https"} and parsed.netloc and not any(ch.isspace() for ch in configured):
                # Preserve the configured path verbatim.  In particular,
                # Django's canonical billing callback routes end in a slash;
                # removing it makes hosted payment providers hit a redirect
                # instead of the callback endpoint configured by the merchant.
                base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))
            else:
                logger.error("Invalid %s payment callback URL; falling back to BASE_URL", setting_name)
                base = f"{self._base_url()}{default_path}"
        else:
            base = f"{self._base_url()}{default_path}"
        if params:
            base = f"{base}?{urlencode(params, doseq=True)}"
        return base

    @staticmethod
    def _reference(prefix, user, subscription_plan):
        plan = str(getattr(subscription_plan, "plan", subscription_plan or "PLAN")).upper()
        plan = "".join(ch for ch in plan if ch.isalnum() or ch in "-_")[:20] or "PLAN"
        return f"{prefix}-{int(getattr(user, 'id', 0) or 0)}-{plan}-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _decimal_string(value):
        return format(Decimal(value).quantize(Decimal("0.01")), "f")

    @staticmethod
    def _drop_none(payload):
        for key in list(payload):
            if payload[key] is None:
                payload.pop(key, None)

    @staticmethod
    def _json_or_error(response):
        try:
            data = response.json()
            return data if isinstance(data, Mapping) else {"error": "Unexpected provider response"}
        except ValueError:
            return {"error": str(getattr(response, "text", ""))[:500]}

    @staticmethod
    def _request_timeout(value):
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            logger.warning("Invalid PAYMENT_HTTP_TIMEOUT; using 20 seconds")
            return 20
        if timeout <= 0:
            logger.warning("Non-positive PAYMENT_HTTP_TIMEOUT; using 20 seconds")
            return 20
        return timeout

    def _intasend_environment_error(self):
        key = str(self.intasend_public_key or "").strip().lower()
        base_host = (urlsplit(str(self.intasend_base_url or "")).hostname or "").lower()
        is_sandbox = base_host == "sandbox.intasend.com" or base_host.endswith(".sandbox.intasend.com")
        is_live = base_host in {"api.intasend.com", "payment.intasend.com"} or (base_host.endswith(".intasend.com") and not is_sandbox)
        key_environment = "sandbox" if "test" in key else "live" if "live" in key else "unknown"
        if key_environment == "sandbox" and not is_sandbox:
            return "IntaSend test credentials require the IntaSend sandbox API URL."
        if key_environment == "live" and not is_live:
            return "IntaSend live credentials require the IntaSend live API URL."
        if base_host and not (is_sandbox or is_live):
            return "IntaSend API URL is not a recognized live or sandbox endpoint."
        return ""

    @staticmethod
    def _provider_request_id(response):
        headers = getattr(response, "headers", {}) or {}
        for name in ("X-Request-ID", "X-Correlation-ID", "X-Request-Id", "Request-ID", "request-id"):
            value = headers.get(name)
            if value:
                return str(value)[:200]
        return ""

    @staticmethod
    def _endpoint_for_log(base_url, path):
        parsed = urlsplit(str(base_url or "").strip())
        hostname = (parsed.hostname or "").lower() or "invalid"
        return f"{hostname}{path}"

    @staticmethod
    def _provider_environment(endpoint):
        host = (urlsplit(endpoint if "://" in str(endpoint) else f"https://{endpoint}").hostname or "").lower()
        if host == "sandbox.intasend.com" or host.endswith(".sandbox.intasend.com"):
            return "sandbox"
        if host in {"api.intasend.com", "payment.intasend.com"} or (host.endswith(".intasend.com") and host != "sandbox.intasend.com"):
            return "live"
        return "unknown"

    @staticmethod
    def _classify_provider_failure(status_code, data):
        if status_code in {401, 403}:
            return "configuration/authentication failure"
        if status_code in {400, 422}:
            return "malformed request"
        if status_code is not None and 400 <= status_code < 500:
            return "provider rejected request"
        if status_code is not None and status_code >= 500:
            return "provider unavailable"
        return "unknown provider failure"

    @classmethod
    def _sanitize_diagnostic_value(cls, key, value):
        sensitive = ("secret", "token", "password", "authorization", "api_key", "access_key", "credential")
        if any(part in str(key).lower() for part in sensitive):
            return "[REDACTED]"
        if key in {"email", "first_name", "last_name", "phone_number"}:
            return "[REDACTED]" if value else None
        if isinstance(value, str):
            return value[:300]
        if isinstance(value, dict):
            return {str(k): cls._sanitize_diagnostic_value(str(k), v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._sanitize_diagnostic_value(str(key), v) for v in value[:10]]
        return value

    @classmethod
    def _log_provider_diagnostic(
        cls, *, provider, endpoint, method, status_code, request_id,
        merchant_reference, plan, currency, amount, recurring, payload,
        response, classification, exception=None,
    ):
        diagnostic = {
            "provider": provider,
            "environment": cls._provider_environment(endpoint),
            "endpoint": endpoint,
            "method": method,
            "http_status": status_code,
            "request_id": request_id or None,
            "checkout_merchant_reference": merchant_reference or None,
            "plan": str(plan or "").upper(),
            "currency": str(currency or "").upper(),
            "amount": cls._decimal_string(amount) if amount is not None else None,
            "recurring": bool(recurring),
            "sanitized_payload": cls._sanitize_diagnostic_value("payload", payload),
            "sanitized_provider_response": cls._sanitize_diagnostic_value("response", response or {}),
            "timestamp": datetime.now(dt_timezone.utc).isoformat(),
            "exception_error_classification": classification,
        }
        if exception is not None:
            diagnostic["exception"] = type(exception).__name__
        logger.error("payment_provider_diagnostic=%s", diagnostic)

    @staticmethod
    def _is_checkout_url(value):
        parsed = urlsplit(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _provider_error(data):
        if isinstance(data, dict) and isinstance(data.get("errors"), list):
            details = [
                item.get("detail") or item.get("message") or item.get("code")
                for item in data["errors"]
                if isinstance(item, dict)
            ]
            if details:
                return "; ".join(str(item) for item in details if item)
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return error.get("message") or error.get("code") or str(error)
        return data.get("message") or data.get("detail") or str(data)

    @staticmethod
    def _configuration_error(variable):
        logger.error("Payment configuration missing: %s", variable)
        return {"url": "", "error": f"Missing payment configuration: {variable}"}

    @classmethod
    def _checkout_http_error(cls, provider, status_code, data):
        name = "IntaSend" if provider == cls.INTASEND else "Pesapal"
        if status_code in {401, 403}:
            return f"{name} rejected the payment credentials. Check the configured production API credentials."
        if status_code == 400:
            return f"{name} rejected the checkout request. Check the merchant configuration and callback settings."
        if status_code == 404:
            return f"{name} checkout endpoint was not found. Check the configured payment API URL."
        if status_code >= 500:
            return f"{name} is temporarily unavailable. Please try again."
        return f"{name} could not create the checkout (HTTP {status_code}). Please try again."

    @staticmethod
    def _parse_payload(payload):
        if isinstance(payload, dict):
            return payload
        import json
        try:
            return json.loads(payload or b"{}")
        except (TypeError, ValueError):
            return {}
