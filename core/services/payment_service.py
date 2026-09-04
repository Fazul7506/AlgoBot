"""Provider-neutral payment integration for IntaSend and Pesapal."""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Optional
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
        self.intasend_base_url = getattr(settings, "INTASEND_API_BASE_URL", "https://api.intasend.com").rstrip("/")
        self.pesapal_consumer_key = getattr(settings, "PESAPAL_CONSUMER_KEY", "")
        self.pesapal_consumer_secret = getattr(settings, "PESAPAL_CONSUMER_SECRET", "")
        self.pesapal_notification_id = getattr(settings, "PESAPAL_NOTIFICATION_ID", "")
        self.pesapal_base_url = getattr(settings, "PESAPAL_API_BASE_URL", "https://pay.pesapal.com/v3").rstrip("/")
        self.timeout = int(getattr(settings, "PAYMENT_HTTP_TIMEOUT", 20))

    def create_checkout_session(self, user, subscription_plan, provider: str | None = None):
        selected = str(provider or self.provider).lower().strip()
        logger.info("Creating %s checkout for %s plan=%s", selected, getattr(user, "username", None), subscription_plan)
        if selected == self.INTASEND:
            return self.create_intasend_checkout(user, subscription_plan)
        if selected == self.PESAPAL:
            return self.create_pesapal_checkout(user, subscription_plan)
        return {"url": "", "provider": selected, "error": "Unsupported payment provider"}

    def create_intasend_checkout(self, user, subscription_plan):
        if not self.intasend_public_key:
            return self._configuration_error("INTASEND_PUBLIC_KEY")
        amount, currency = self._amount_and_currency(subscription_plan)
        api_ref = self._reference("IS", user, subscription_plan)
        redirect_url = self._callback_url(
            "BILLING_SUCCESS_URL",
            "/billing/success/",
            {"provider": self.INTASEND, "reference": api_ref},
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
            "mobile_tarrif": "BUSINESS-PAYS",
            "card_tarrif": "BUSINESS-PAYS",
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
            if not response.ok:
                logger.error("IntaSend checkout failed: %s", data)
                return {"url": "", "provider": self.INTASEND, "error": self._provider_error(data)}
            url = data.get("url") or data.get("checkout_url") or data.get("link") or ""
            invoice_id = data.get("invoice_id") or data.get("id") or data.get("checkout_id")
            if not url:
                logger.error("IntaSend checkout returned success without a checkout URL: %s", data)
                return {"url": "", "provider": self.INTASEND, "error": "Payment provider returned no checkout URL"}
            return {
                "provider": self.INTASEND,
                "session_id": invoice_id or api_ref,
                "invoice_id": invoice_id,
                "reference": api_ref,
                "url": url,
            }
        except requests.RequestException as exc:
            logger.exception("IntaSend checkout request failed")
            return {"url": "", "provider": self.INTASEND, "error": str(exc)}

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
            "amount": float(amount),
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
                logger.error("Pesapal order failed: %s", data)
                return {"url": "", "provider": self.PESAPAL, "error": self._provider_error(data)}
            url = data.get("redirect_url") or data.get("url") or ""
            tracking_id = data.get("order_tracking_id") or data.get("tracking_id")
            if not url or not tracking_id:
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
            return {"url": "", "provider": self.PESAPAL, "error": str(exc)}

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
                base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
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
            return response.json()
        except ValueError:
            return {"error": response.text[:500]}

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

    @staticmethod
    def _parse_payload(payload):
        if isinstance(payload, dict):
            return payload
        import json
        try:
            return json.loads(payload or b"{}")
        except (TypeError, ValueError):
            return {}
