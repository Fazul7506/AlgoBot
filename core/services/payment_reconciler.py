from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.models import Invoice, Payment, ReferralReward, Subscription
from core.services.payment_service import PaymentService


class PaymentReconciler:
    """Persist provider callbacks using the canonical Payment model states."""

    SUCCESS = {"COMPLETE", "COMPLETED", "SUCCESS", "SUCCEEDED", "PAID"}
    FAILED = {"FAILED", "FAILURE", "INVALID", "REVERSED", "CANCELLED", "CANCELED"}

    @staticmethod
    def normalize_status(value):
        value = str(value or "").strip().upper()
        if value in PaymentReconciler.SUCCESS:
            return "COMPLETED"
        if value in PaymentReconciler.FAILED:
            return "FAILED"
        return "PENDING"

    @staticmethod
    def _minor_units(value):
        try:
            return int((Decimal(str(value or 0)) * Decimal("100")).quantize(Decimal("1")))
        except (InvalidOperation, ValueError, TypeError):
            return 0

    @staticmethod
    def _reference_parts(reference):
        parts = str(reference or "").split("-")
        if len(parts) < 3 or parts[0] not in {"IS", "PP"}:
            return None, ""
        try:
            user_id = int(parts[1])
        except (TypeError, ValueError):
            return None, ""
        return user_id, parts[2].upper()

    @classmethod
    def _resolve_user_and_plan(cls, metadata, invoice=None):
        metadata = metadata if isinstance(metadata, dict) else {}
        plan = str(metadata.get("plan") or metadata.get("plan_key") or "").upper()
        user_id = metadata.get("user_id") or metadata.get("userId")
        nested = metadata.get("metadata")
        if isinstance(nested, dict):
            nested_user, nested_plan = cls._resolve_user_and_plan(nested, invoice=invoice)
            user_id = user_id or nested_user
            plan = plan or nested_plan
        reference = metadata.get("api_ref") or metadata.get("reference") or metadata.get("merchant_reference") or metadata.get("OrderMerchantReference")
        ref_user, ref_plan = cls._reference_parts(reference)
        user_id = user_id or ref_user
        plan = plan or ref_plan
        if invoice:
            invoice_meta = invoice.metadata or {}
            invoice_user, invoice_plan = cls._resolve_user_and_plan(invoice_meta)
            user_id = user_id or invoice.user_id or invoice_user
            plan = plan or invoice_plan
        try:
            user_id = int(user_id) if user_id else None
        except (TypeError, ValueError):
            user_id = None
        return user_id, plan

    @classmethod
    def reconcile(cls, *, provider, external_id, status, amount=None, currency="KES", metadata=None):
        metadata = metadata if isinstance(metadata, dict) else {}
        external_id = str(external_id or "").strip()
        if not external_id:
            return None
        user_id, plan_key = cls._resolve_user_and_plan(metadata)
        user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
        if not user:
            return {"received": True, "provider": provider, "status": cls.normalize_status(status), "external_id": external_id, "unresolved_user": True}

        normalized = cls.normalize_status(status)
        amount_minor = cls._minor_units(amount)
        currency = str(currency or "KES").lower()
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().filter(external_id=external_id).first()
            if not invoice:
                invoice = Invoice.objects.create(
                    user=user,
                    external_id=external_id,
                    amount_cents=amount_minor,
                    currency=currency,
                    paid=False,
                    metadata={"provider": provider, "payment": metadata, "plan": plan_key},
                )
            elif invoice.user_id != user.id:
                return {"received": True, "provider": provider, "status": normalized, "external_id": external_id, "rejected": "invoice_owner_mismatch"}

            if plan_key and not (invoice.metadata or {}).get("plan"):
                invoice.metadata = {**(invoice.metadata or {}), "plan": plan_key}
            invoice.metadata = {**(invoice.metadata or {}), "provider": provider, "payment": metadata}
            if amount_minor:
                invoice.amount_cents = amount_minor
            invoice.currency = currency

            payment = Payment.objects.select_for_update().filter(external_id=external_id).first()
            was_completed = bool(payment and (payment.status == "COMPLETED" or invoice.paid))
            if not payment:
                payment = Payment.objects.create(user=user, invoice=invoice, external_id=external_id, amount_cents=amount_minor, currency=currency, status="PENDING")
            elif payment.user_id != user.id:
                return {"received": True, "provider": provider, "status": normalized, "external_id": external_id, "rejected": "payment_owner_mismatch"}

            payment.invoice = invoice
            payment.amount_cents = amount_minor or payment.amount_cents
            payment.currency = currency
            payment.status = normalized
            payment.save(update_fields=["invoice", "amount_cents", "currency", "status"])

            if normalized == "COMPLETED":
                invoice.paid = True
                invoice.save(update_fields=["paid", "amount_cents", "currency", "metadata"])
                if not was_completed:
                    cls._activate_subscription_and_referral(user, invoice, plan_key)
            else:
                invoice.save(update_fields=["amount_cents", "currency", "metadata"])

        return {"received": True, "provider": provider, "status": normalized, "external_id": external_id, "payment_id": payment.id}

    @classmethod
    def _activate_subscription_and_referral(cls, user, invoice, plan_key):
        plan = plan_key if plan_key in {choice[0] for choice in Subscription.PLAN_CHOICES} else ""
        subscription, _ = Subscription.objects.select_for_update().get_or_create(user=user)
        if plan:
            subscription.plan = plan
        subscription.price_cents = invoice.amount_cents
        subscription.currency = str(invoice.currency or "KES").lower()
        subscription.recurring = plan != "FREE"
        subscription.is_active = True
        subscription.renewed_at = timezone.now()
        subscription.expires_at = timezone.now() + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30))) if subscription.recurring else None
        subscription.save()

        profile = getattr(user, "trading_profile", None)
        referrer = getattr(profile, "referred_by", None) if profile else None
        if not referrer:
            return
        reward_amount = float(getattr(settings, "REFERRAL_CREDIT_AMOUNT", 0.0) or 0.0)
        if reward_amount <= 0:
            reward_amount = (invoice.amount_cents / 100.0) * 0.05
        reward, created = ReferralReward.objects.get_or_create(referrer=referrer, referee=user, defaults={"amount_credits": reward_amount})
        if created:
            profile.referral_credits = (profile.referral_credits or 0.0) + reward_amount
            profile.save(update_fields=["referral_credits"])

    @classmethod
    def handle_intasend_webhook(cls, payload):
        data = PaymentService._parse_payload(payload)
        challenge = str(data.get("challenge", ""))
        configured_challenge = str(getattr(settings, "INTASEND_WEBHOOK_CHALLENGE", "") or "")
        if configured_challenge and challenge != configured_challenge:
            return None
        invoice_id = data.get("invoice_id")
        api_ref = data.get("api_ref") or data.get("reference")
        external_id = invoice_id or api_ref
        if not external_id:
            return None
        return cls.reconcile(provider="intasend", external_id=external_id, status=data.get("state"), amount=data.get("value") or data.get("amount") or data.get("net_amount"), currency=data.get("currency", "KES"), metadata=data)

    @classmethod
    def handle_pesapal_webhook(cls, payload):
        data = PaymentService._parse_payload(payload)
        tracking_id = data.get("OrderTrackingId") or data.get("orderTrackingId") or data.get("order_tracking_id")
        merchant_reference = data.get("OrderMerchantReference") or data.get("orderMerchantReference") or data.get("merchant_reference") or ""
        if not tracking_id:
            return None
        status = PaymentService().get_pesapal_transaction_status(str(tracking_id))
        if not status:
            return None
        result = cls.reconcile(provider="pesapal", external_id=tracking_id, status=status.get("payment_status_description"), amount=status.get("amount"), currency=status.get("currency", "KES"), metadata={"merchant_reference": merchant_reference, "pesapal": status})
        if result is not None:
            result["ipn_ack"] = {"orderNotificationType": data.get("OrderNotificationType") or data.get("orderNotificationType") or "IPNCHANGE", "orderTrackingId": tracking_id, "orderMerchantReference": merchant_reference, "status": 200}
        return result

    @classmethod
    def handle_pesapal_callback(cls, tracking_id, merchant_reference):
        if not tracking_id:
            return None
        status = PaymentService().get_pesapal_transaction_status(str(tracking_id))
        if not status:
            return None
        return cls.reconcile(provider="pesapal", external_id=tracking_id, status=status.get("payment_status_description"), amount=status.get("amount"), currency=status.get("currency", "KES"), metadata={"merchant_reference": merchant_reference, "pesapal": status})
