"""Provider-neutral payment integration for IntaSend and Pesapal.

The billing models are intentionally left unchanged in this integration.
The existing legacy provider-reference field remains in the schema for
backwards compatibility, but it is not used by the payment providers below.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class PaymentService:
    """Create and reconcile checkout payments through IntaSend and Pesapal."""

    INTASEND = "intasend"
    PESAPAL = "pesapal"

    def __init__(self):
        self.provider = str(getattr(settings, "PAYMENT_PROVIDER", self.INTASEND)).lower()
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
        redirect_url = self._callback_url("BILLING_SUCCESS_URL", "/billing/success/")
        host_url = self._base_url()
        payload = {
            "amount": self._decimal_string(amount), "currency": currency.upper(), "api_ref": api_ref,
            "email": getattr(user, "email", "") or None, "first_name": getattr(user, "first_name", "") or None,
            "last_name": getattr(user, "last_name", "") or None, "country": "KE" if currency.upper() == "KES" else None,
            "channel": "WEBSITE", "host": host_url, "redirect_url": redirect_url,
            "mobile_tarrif": "BUSINESS-PAYS", "card_tarrif": "BUSINESS-PAYS",
        }
        self._drop_none(payload)
        try:
            response = requests.post(f"{self.intasend_base_url}/api/v1/checkout/", json=payload, headers={"X-IntaSend-Public-API-Key": self.intasend_public_key, "Content-Type": "application/json", "Accept": "application/json"}, timeout=self.timeout)
            data = self._json_or_error(response)
            if not response.ok:
                logger.error("IntaSend checkout failed: %s", data)
                return {"url": "", "provider": self.INTASEND, "error": self._provider_error(data)}
            url = data.get("url") or data.get("checkout_url") or data.get("link") or ""
            invoice_id = data.get("invoice_id") or data.get("id") or data.get("checkout_id")
            return {"provider": self.INTASEND, "session_id": invoice_id or api_ref, "invoice_id": invoice_id, "reference": api_ref, "url": url}
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
        # Pesapal validates callback/cancellation URLs as absolute provider-safe
        # URLs. Never forward query strings/fragments or malformed BASE_URL data.
        callback_url = self._callback_url("PESAPAL_CALLBACK_URL", "/payments/pesapal/callback/")
        cancellation_url = self._callback_url("PESAPAL_CANCELLATION_URL", "/billing/cancel/")
        token = self._pesapal_access_token()
        if not token:
            return {"url": "", "provider": self.PESAPAL, "error": "Unable to authenticate with Pesapal"}
        billing_address = {
            "email_address": getattr(user, "email", "") or "", "phone_number": getattr(getattr(user, "trading_profile", None), "phone", "") or "",
            "country_code": "KE" if currency.upper() == "KES" else "", "first_name": getattr(user, "first_name", "") or getattr(user, "username", "Customer"),
            "middle_name": "", "last_name": getattr(user, "last_name", "") or "", "line_1": "", "line_2": "", "city": "", "state": "", "postal_code": "", "zip_code": "",
        }
        payload = {"id": reference, "currency": currency.upper(), "amount": float(amount), "description": f"AlgoBot {getattr(subscription_plan, 'plan', subscription_plan)} subscription", "callback_url": callback_url, "cancellation_url": cancellation_url, "notification_id": self.pesapal_notification_id, "billing_address": billing_address}
        if getattr(subscription_plan, "recurring", False):
            payload["account_number"] = f"ALGOBOT-{user.id}"
        try:
            response = requests.post(f"{self.pesapal_base_url}/api/Transactions/SubmitOrderRequest", json=payload, headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}, timeout=self.timeout)
            data = self._json_or_error(response)
            if not response.ok:
                logger.error("Pesapal order failed: %s", data)
                return {"url": "", "provider": self.PESAPAL, "error": self._provider_error(data)}
            url = data.get("redirect_url") or data.get("url") or ""
            tracking_id = data.get("order_tracking_id") or data.get("tracking_id")
            return {"provider": self.PESAPAL, "session_id": tracking_id or reference, "order_tracking_id": tracking_id, "reference": reference, "url": url}
        except requests.RequestException as exc:
            logger.exception("Pesapal checkout request failed")
            return {"url": "", "provider": self.PESAPAL, "error": str(exc)}

    def handle_webhook(self, payload: bytes | dict, sig_header: str = "", provider: str | None = None) -> Optional[dict]:
        selected = str(provider or self.provider).lower().strip()
        data = self._parse_payload(payload)
        if selected == self.INTASEND:
            return self._handle_intasend_webhook(data)
        if selected == self.PESAPAL:
            return self._handle_pesapal_webhook(data)
        logger.warning("Received webhook for unsupported provider %s", selected)
        return None

    def handle_pesapal_callback(self, order_tracking_id: str, merchant_reference: str = ""):
        status = self.get_pesapal_transaction_status(order_tracking_id)
        if status:
            return self._reconcile_status(provider=self.PESAPAL, external_id=order_tracking_id, status=self._normalise_status(status.get("payment_status_description")), amount=status.get("amount"), currency=status.get("currency", "KES"), metadata={"merchant_reference": merchant_reference, "pesapal": status})
        return None

    def get_pesapal_transaction_status(self, order_tracking_id: str) -> Optional[dict]:
        token = self._pesapal_access_token()
        if not token or not order_tracking_id:
            return None
        try:
            response = requests.get(f"{self.pesapal_base_url}/api/Transactions/GetTransactionStatus", params={"orderTrackingId": order_tracking_id}, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=self.timeout)
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
            response = requests.post(f"{self.intasend_base_url}/api/v1/payment/status/", json={"invoice_id": invoice_id}, headers={"Authorization": f"Bearer {self.intasend_secret_key}", "Content-Type": "application/json", "Accept": "application/json"}, timeout=self.timeout)
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

    def _handle_intasend_webhook(self, data: dict) -> Optional[dict]:
        challenge = str(data.get("challenge", ""))
        if self.intasend_webhook_challenge and challenge != self.intasend_webhook_challenge:
            logger.warning("IntaSend webhook challenge mismatch")
            return None
        state = self._normalise_status(data.get("state"))
        invoice_id = data.get("invoice_id")
        api_ref = data.get("api_ref") or data.get("reference")
        external_id = invoice_id or api_ref
        if not external_id:
            return None
        return self._reconcile_status(provider=self.INTASEND, external_id=str(external_id), status=state, amount=data.get("value") or data.get("amount") or data.get("net_amount"), currency=data.get("currency", "KES"), metadata=data)

    def _handle_pesapal_webhook(self, data: dict) -> Optional[dict]:
        tracking_id = data.get("OrderTrackingId") or data.get("orderTrackingId") or data.get("order_tracking_id")
        merchant_reference = data.get("OrderMerchantReference") or data.get("orderMerchantReference") or data.get("merchant_reference") or ""
        if not tracking_id:
            return None
        status = self.get_pesapal_transaction_status(str(tracking_id))
        if not status:
            return None
        result = self._reconcile_status(provider=self.PESAPAL, external_id=str(tracking_id), status=self._normalise_status(status.get("payment_status_description")), amount=status.get("amount"), currency=status.get("currency", "KES"), metadata={"merchant_reference": merchant_reference, "pesapal": status}) or {}
        result["ipn_ack"] = {"orderNotificationType": data.get("OrderNotificationType") or data.get("orderNotificationType") or "IPNCHANGE", "orderTrackingId": tracking_id, "orderMerchantReference": merchant_reference, "status": 200}
        return result

    def _pesapal_access_token(self) -> Optional[str]:
        cache_key = "algobot:pesapal:access_token"
        try:
            cached = cache.get(cache_key)
            if cached:
                return str(cached)
        except Exception:
            logger.warning("Pesapal token cache unavailable; requesting a fresh token")
        try:
            response = requests.post(f"{self.pesapal_base_url}/api/Auth/RequestToken", json={"consumer_key": self.pesapal_consumer_key, "consumer_secret": self.pesapal_consumer_secret}, headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=self.timeout)
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

    def _reconcile_status(self, *, provider, external_id, status, amount, currency, metadata):
        from django.contrib.auth import get_user_model
        from core.models import Invoice, Payment, ReferralReward, Subscription
        User = get_user_model()
        user_id = self._user_id_from_metadata(metadata)
        user = User.objects.filter(id=user_id).first() if user_id else None
        if not user:
            logger.warning("Payment %s has no resolvable AlgoBot user", external_id)
            return {"received": True, "provider": provider, "status": status, "external_id": external_id}
        amount_minor = self._to_minor_units(amount)
        currency = str(currency or "KES").lower()
        succeeded = status == "succeeded"
        payment_status = "COMPLETED" if succeeded else ("FAILED" if status == "failed" else "PENDING")
        invoice, _ = Invoice.objects.get_or_create(user=user, external_id=str(external_id), defaults={"amount_cents": amount_minor, "currency": currency, "paid": succeeded, "metadata": {"provider": provider, "payment": metadata}})
        if succeeded and not invoice.paid:
            invoice.paid = True; invoice.amount_cents = amount_minor; invoice.currency = currency; invoice.metadata = {"provider": provider, "payment": metadata}; invoice.save(update_fields=["paid", "amount_cents", "currency", "metadata"])
        payment, created = Payment.objects.get_or_create(user=user, external_id=str(external_id), defaults={"invoice": invoice, "amount_cents": amount_minor, "currency": currency, "status": payment_status})
        was_succeeded = payment.status == "COMPLETED"
        if payment.status != payment_status or payment.invoice_id != invoice.id:
            payment.status = payment_status; payment.invoice = invoice; payment.amount_cents = amount_minor; payment.currency = currency; payment.save(update_fields=["status", "invoice", "amount_cents", "currency"])
        if succeeded and (created or not was_succeeded):
            self._activate_subscription_and_referral(user, metadata, amount_minor, currency, provider)
        return {"received": True, "provider": provider, "status": status, "external_id": str(external_id), "payment_id": payment.id}

    def _activate_subscription_and_referral(self, user, metadata, amount_minor, currency, provider):
        from core.models import ReferralReward, Subscription
        plan_key = self._plan_from_metadata(metadata)
        try:
            sub, _ = Subscription.objects.get_or_create(user=user)
            if plan_key and plan_key in {choice[0] for choice in Subscription.PLAN_CHOICES}:
                sub.plan = plan_key
            sub.price_cents = int(amount_minor)
            sub.currency = str(currency or "KES")
            sub.recurring = sub.plan != "FREE"
            sub.is_active = True
            sub.renewed_at = timezone.now()
            sub.expires_at = sub.renewed_at + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30))) if sub.recurring else None
            sub.save(update_fields=["plan", "price_cents", "currency", "recurring", "is_active", "renewed_at", "expires_at"])
        except Exception:
            logger.exception("Failed to update subscription for user %s", getattr(user, "username", None))
        try:
            profile = getattr(user, "trading_profile", None)
            if profile and getattr(profile, "referred_by", None):
                credit_amount = getattr(settings, "REFERRAL_CREDIT_AMOUNT", 0.0)
                if credit_amount <= 0: credit_amount = (int(amount_minor) / 100.0) * 0.05
                profile.referral_credits = (profile.referral_credits or 0.0) + float(credit_amount); profile.save(update_fields=["referral_credits"])
                ReferralReward.objects.get_or_create(referrer=profile.referred_by, referee=user, defaults={"amount_credits": float(credit_amount)})
        except Exception:
            logger.exception("Failed to award referral credit for user %s", getattr(user, "username", None))

    def _amount_and_currency(self, subscription_plan):
        raw_amount = getattr(subscription_plan, "price_cents", 0) if not isinstance(subscription_plan, str) else 0
        currency = getattr(subscription_plan, "currency", "KES") if not isinstance(subscription_plan, str) else "KES"
        try: amount = Decimal(str(raw_amount or 0)) / Decimal("100")
        except (InvalidOperation, ValueError): amount = Decimal("0")
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
                # Keep the configured endpoint, while rebuilding query values
                # from trusted provider parameters below.
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
    def _decimal_string(value): return format(Decimal(value).quantize(Decimal("0.01")), "f")

    @staticmethod
    def _drop_none(payload):
        for key in list(payload):
            if payload[key] is None: payload.pop(key, None)

    @staticmethod
    def _json_or_error(response):
        try: return response.json()
        except ValueError: return {"error": response.text[:500]}

    @staticmethod
    def _provider_error(data):
        if isinstance(data, dict) and isinstance(data.get("errors"), list):
            details = [item.get("detail") or item.get("message") or item.get("code") for item in data["errors"] if isinstance(item, dict)]
            if details: return "; ".join(str(item) for item in details if item)
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict): return error.get("message") or error.get("code") or str(error)
        return data.get("message") or data.get("detail") or str(data)

    @staticmethod
    def _configuration_error(variable):
        logger.error("Payment configuration missing: %s", variable)
        return {"url": "", "error": f"Missing payment configuration: {variable}"}

    @staticmethod
    def _parse_payload(payload):
        if isinstance(payload, dict): return payload
        import json
        try: return json.loads(payload or b"{}")
        except (TypeError, ValueError): return {}

    @staticmethod
    def _normalise_status(value):
        value = str(value or "").strip().lower()
        if value in {"completed", "complete", "paid", "successful", "success", "succeeded"}: return "succeeded"
        if value in {"failed", "failure", "cancelled", "canceled", "invalid", "reversed"}: return "failed"
        return "pending"

    @staticmethod
    def _to_minor_units(amount):
        try: return int((Decimal(str(amount or 0)) * Decimal("100")).quantize(Decimal("1")))
        except (InvalidOperation, ValueError): return 0

    @staticmethod
    def _user_id_from_metadata(metadata):
        if not isinstance(metadata, dict): return None
        for key in ("user_id", "userid", "merchant_reference", "api_ref", "reference", "orderMerchantReference", "OrderMerchantReference"):
            value = metadata.get(key)
            if value:
                text = str(value)
                parts = text.split("-")
                for part in parts:
                    if part.isdigit(): return int(part)
        nested = metadata.get("pesapal")
        if isinstance(nested, dict): return PaymentService._user_id_from_metadata(nested)
        return None

    @staticmethod
    def _plan_from_metadata(metadata):
        if not isinstance(metadata, dict): return ""
        for key in ("plan", "subscription_plan"):
            value = metadata.get(key)
            if value: return str(value).upper()
        for key in ("api_ref", "reference", "merchant_reference", "OrderMerchantReference", "orderMerchantReference"):
            value = metadata.get(key)
            if value:
                parts = str(value).split("-")
                if len(parts) >= 3: return parts[2].upper()
        nested = metadata.get("pesapal")
        if isinstance(nested, dict): return PaymentService._plan_from_metadata(nested)
        return ""
