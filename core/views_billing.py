"""Authenticated billing API and provider checkout callback pages."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse
from django.urls import reverse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Invoice, Payment, Subscription
from core.services.payment_reconciler import PaymentReconciler
from core.services.payment_service import PaymentService


@dataclass(frozen=True)
class CheckoutPlan:
    plan: str
    price_cents: int
    currency: str = "KES"
    recurring: bool = True
    reference: str = ""


class RequestBoundPaymentService(PaymentService):
    def __init__(self, request):
        self._request = request
        super().__init__()

    def _base_url(self):
        configured = str(getattr(settings, "BASE_URL", "") or "").split(",")[0].strip().rstrip("/")
        parsed = urlparse(configured)
        host = self._request.get_host().split(":", 1)[0]
        local_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        if parsed.scheme == "https" and parsed.netloc and (parsed.hostname or "").lower() not in local_hosts:
            return configured
        scheme = "https" if not settings.DEBUG else self._request.scheme
        return f"{scheme}://{host}".rstrip("/")


def _safe_price(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _plans():
    currency = str(getattr(settings, "ALGOBOT_BILLING_CURRENCY", "KES")).upper()
    configured = {"BASIC": _safe_price(getattr(settings, "ALGOBOT_BASIC_PRICE_CENTS", None)), "PRO": _safe_price(getattr(settings, "ALGOBOT_PRO_PRICE_CENTS", None)), "ENTERPRISE": _safe_price(getattr(settings, "ALGOBOT_ENTERPRISE_PRICE_CENTS", None))}
    plans = [{"plan": "FREE", "price_cents": 0, "currency": currency, "recurring": False, "configured": True}]
    for name, price in configured.items():
        plans.append({"plan": name, "price_cents": price, "currency": currency, "recurring": True, "configured": price is not None and price > 0})
    return plans


def _plan(name):
    wanted = str(name or "").upper().strip()
    return next((item for item in _plans() if item["plan"] == wanted), None)


def _subscription_snapshot(subscription):
    now = timezone.now()
    expired = bool(subscription.expires_at and subscription.expires_at <= now)
    if expired and subscription.is_active:
        subscription.is_active = False
        subscription.save(update_fields=["is_active"])
    return {"plan": subscription.plan, "price_cents": subscription.price_cents, "currency": subscription.currency, "is_active": bool(subscription.is_active and not expired), "recurring": bool(subscription.recurring and subscription.is_active and not expired), "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None}


def _provider_state(result, provider):
    data = result or {}
    if provider == PaymentService.INTASEND and isinstance(data.get("invoice"), dict):
        data = {**data, **data["invoice"]}
    if provider == PaymentService.PESAPAL:
        return str(data.get("payment_status_description", "")).upper(), data
    # IntaSend collection responses expose state while recurring subscription
    # responses expose status. Support both authoritative response shapes.
    return str(data.get("state") or data.get("status") or "").upper(), data


def _reconcile_invoice(invoice, provider):
    plan = _plan((invoice.metadata or {}).get("plan"))
    if not plan:
        return {"paid": False, "state": "INVALID_PLAN", "invoice": invoice, "subscription": None}
    service = PaymentService()
    provider = str(provider or (invoice.metadata or {}).get("provider") or service.provider).lower().strip()
    if provider == service.PESAPAL:
        tracking = (invoice.metadata or {}).get("tracking_id") or invoice.external_id
        result = service.get_pesapal_transaction_status(str(tracking)) if tracking else None
    elif provider == service.INTASEND:
        invoice_meta = invoice.metadata or {}
        subscription_id = invoice_meta.get("subscription_id")
        if subscription_id:
            # Recurring plans create an IntaSend subscription; query that
            # subscription directly instead of treating its ID as a collection
            # invoice ID.
            result = service.get_intasend_subscription_status(str(subscription_id))
        else:
            result = service.get_intasend_payment_status(invoice.external_id) if invoice.external_id else None
    else:
        return {"paid": False, "state": "UNSUPPORTED_PROVIDER", "invoice": invoice, "subscription": None}
    provider_state, payload = _provider_state(result, provider)
    metadata = {**(invoice.metadata or {}), "provider": provider, "user_id": invoice.user_id, "plan": plan["plan"], "provider_status": payload}
    if provider == service.PESAPAL:
        metadata["merchant_reference"] = metadata.get("reference") or metadata.get("merchant_reference")
        metadata["tracking_id"] = (invoice.metadata or {}).get("tracking_id") or invoice.external_id
    # IntaSend recurring subscriptions report successful initial payment as
    # ACTIVE (and may also report COMPLETE). Translate only those success
    # states into the canonical payment state; never treat PENDING/PROCESSING
    # as paid.
    reconciler_state = "COMPLETE" if provider == service.INTASEND and provider_state in {"ACTIVE", "COMPLETE"} else provider_state
    normalized = PaymentReconciler.normalize_status(reconciler_state)
    external_id = invoice.external_id or metadata.get("tracking_id")
    reconciled = PaymentReconciler.reconcile(provider=provider, external_id=external_id, status=normalized, amount=payload.get("amount") or payload.get("value") or payload.get("net_amount"), currency=payload.get("currency") or invoice.currency, metadata=metadata)
    subscription = Subscription.objects.filter(user=invoice.user).first()
    return {"paid": normalized == "COMPLETED", "state": provider_state or normalized, "invoice": Invoice.objects.get(pk=invoice.pk), "subscription": subscription, "provider_payload": payload, "reconciled": reconciled}


def _find_callback_invoice(request, reference="", tracking_id=""):
    qs = Invoice.objects.filter(user=request.user) if request.user.is_authenticated else Invoice.objects.none()
    if tracking_id:
        invoice = qs.filter(external_id=tracking_id).first() or qs.filter(metadata__tracking_id=tracking_id).first()
        if invoice:
            return invoice
    if reference:
        invoice = qs.filter(metadata__reference=reference).first()
        if invoice:
            return invoice
    return None


def billing_success_page(request):
    provider = str(request.GET.get("provider", "")).lower().strip()
    reference = str(request.GET.get("reference") or request.GET.get("OrderMerchantReference") or "").strip()
    # IntaSend only permits a restricted character set in redirect_url and
    # rejects query strings containing '&'. Infer IntaSend from our reference
    # prefix when the callback contains the single safe reference parameter.
    if not provider and reference.upper().startswith("IS-"):
        provider = PaymentService.INTASEND
    tracking_id = str(request.GET.get("tracking_id") or request.GET.get("OrderTrackingId") or "").strip()
    invoice = _find_callback_invoice(request, reference, tracking_id)
    result = None
    if invoice and provider:
        try:
            result = _reconcile_invoice(invoice, provider)
        except (IntegrityError, ValueError, KeyError, Invoice.DoesNotExist):
            result = {"paid": bool(invoice.paid), "state": "PENDING", "invoice": invoice, "subscription": Subscription.objects.filter(user=invoice.user).first()}
    elif invoice:
        result = {"paid": bool(invoice.paid), "state": "COMPLETE" if invoice.paid else "PENDING", "invoice": invoice, "subscription": Subscription.objects.filter(user=invoice.user).first()}
    callback_invoice = (result or {}).get("invoice")
    return render(request, "core/billing_success.html", {"provider": provider or "payment provider", "payment_state": (result or {}).get("state", "PENDING"), "payment_paid": bool((result or {}).get("paid")), "invoice": callback_invoice, "invoice_amount": (float(callback_invoice.amount_cents) / 100) if callback_invoice else None, "subscription": (result or {}).get("subscription"), "reference": reference, "tracking_id": tracking_id})


def billing_cancel_page(request):
    return render(request, "core/billing_cancel.html", {"provider": request.GET.get("provider", "payment provider")})


def _checkout(request, plan_name, provider=None):
    plan = _plan(plan_name)
    if not plan:
        return None, "Unknown subscription plan."
    if plan["plan"] == "FREE":
        return None, "FREE does not require payment."
    if not plan["configured"]:
        return None, f"{plan['plan']} is not configured for checkout yet."
    selected = str(provider or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower().strip()
    if selected not in {PaymentService.INTASEND, PaymentService.PESAPAL}:
        return None, "Unsupported payment provider."

    # Serialize checkout initiation per user, but never hold a DB lock across the provider HTTP call.
    # A short-lived lease prevents concurrent browser retries from opening two provider checkouts.
    lease_seconds = 120
    existing_open_id = None
    with transaction.atomic():
        request_user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        existing = (
            Invoice.objects.filter(
                user=request_user,
                paid=False,
                amount_cents=plan["price_cents"],
                currency=plan["currency"],
                metadata__plan=plan["plan"],
                metadata__provider=selected,
            )
            .order_by("-created_at")
            .first()
        )
        metadata = dict(existing.metadata or {}) if existing else {}
        # Hosted checkout URLs can contain bearer-like provider tokens. Never persist
        # or reuse them; a fresh provider response is required for each new checkout.
        metadata.pop("checkout_url", None)
        if existing and metadata.get("state") == "checkout_open":
            existing_open_id = existing.pk
        else:
            now = timezone.now()
            lock_until = metadata.get("checkout_lock_until")
            if existing and metadata.get("state") == "checkout_attempting" and lock_until:
                try:
                    lock_expiry = datetime.fromisoformat(str(lock_until))
                except (TypeError, ValueError):
                    lock_expiry = None
                if lock_expiry and lock_expiry > now:
                    return None, "A checkout is already being started. Please wait for the current checkout attempt."
            invoice = existing or Invoice.objects.create(
                user=request_user,
                amount_cents=plan["price_cents"],
                currency=plan["currency"],
                metadata={"plan": plan["plan"], "provider": selected},
            )
            reference = str(metadata.get("reference") or PaymentService._reference("IS" if selected == PaymentService.INTASEND else "PP", request_user, plan["plan"]))
            invoice.metadata = {
                **metadata,
                "plan": plan["plan"],
                "provider": selected,
                "state": "checkout_attempting",
                "reference": reference,
                "attempt_count": int(metadata.get("attempt_count") or 0) + 1,
                "checkout_lock_until": (now + timedelta(seconds=lease_seconds)).isoformat(),
            }
            invoice.save(update_fields=["metadata"])

    # A previously opened hosted checkout is not reusable from our database because
    # its URL is intentionally never persisted. Ask the provider for the authoritative
    # status before deciding whether another checkout may be created.
    if existing_open_id is not None:
        existing_open = Invoice.objects.filter(pk=existing_open_id, user=request.user).first()
        if not existing_open:
            return None, "The existing checkout could not be found. Please refresh and try again."
        try:
            provider_result = _reconcile_invoice(existing_open, selected)
        except Exception:
            provider_result = None

        provider_state = str((provider_result or {}).get("state") or "").upper()
        if provider_result and provider_result.get("paid"):
            return None, "This checkout has already completed. Refresh billing to see the updated subscription."
        if provider_state not in {"FAILED", "CANCELLED", "REVERSED", "INVALID"}:
            # For an IntaSend recurring checkout that is still PENDING or
            # PROCESSING, the provider may return the current setup_url. Resume
            # that authoritative checkout rather than trapping the user behind
            # a stale local checkout_open state.
            provider_payload = provider_result.get("provider_payload") if provider_result else None
            resume_url = provider_payload.get("setup_url") if isinstance(provider_payload, dict) else None
            parsed_resume_url = urlparse(str(resume_url or ""))
            if (
                provider_state in {"PENDING", "PROCESSING"}
                and parsed_resume_url.scheme in {"http", "https"}
                and parsed_resume_url.netloc
            ):
                return str(resume_url), None
            return None, "A checkout is already open. Complete it or wait for its provider status before starting another checkout."

        # The provider has reached a terminal non-success state. Atomically claim the
        # invoice for a fresh attempt so concurrent browser retries cannot both start one.
        with transaction.atomic():
            request_user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            invoice = Invoice.objects.select_for_update().filter(pk=existing_open_id, user=request_user, paid=False).first()
            if not invoice:
                return None, "The existing checkout changed while it was being checked. Refresh billing and try again."
            metadata = dict(invoice.metadata or {})
            if metadata.get("state") == "checkout_open":
                now = timezone.now()
                metadata.update({
                    "state": "checkout_attempting",
                    "checkout_lock_until": (now + timedelta(seconds=lease_seconds)).isoformat(),
                    "error": "",
                    "error_classification": "",
                })
                invoice.metadata = metadata
                invoice.save(update_fields=["metadata"])
            elif metadata.get("state") == "checkout_attempting":
                lock_until = metadata.get("checkout_lock_until")
                try:
                    lock_expiry = datetime.fromisoformat(str(lock_until))
                except (TypeError, ValueError):
                    lock_expiry = None
                if lock_expiry and lock_expiry > timezone.now():
                    return None, "A checkout is already being started. Please wait for the current checkout attempt."
            reference = str(metadata.get("reference") or PaymentService._reference("IS" if selected == PaymentService.INTASEND else "PP", request_user, plan["plan"]))
            invoice.metadata = {
                **metadata,
                "plan": plan["plan"],
                "provider": selected,
                "reference": reference,
                "attempt_count": int(metadata.get("attempt_count") or 0) + 1,
                "checkout_lock_until": (timezone.now() + timedelta(seconds=lease_seconds)).isoformat(),
            }
            invoice.save(update_fields=["metadata"])

    else:
        invoice = locals().get("invoice")
        if invoice is None:
            return None, "Checkout could not be initialized. Please refresh and try again."
        request_user = get_user_model().objects.get(pk=request.user.pk)
        reference = str((invoice.metadata or {}).get("reference") or PaymentService._reference("IS" if selected == PaymentService.INTASEND else "PP", request_user, plan["plan"]))

    try:
        result = RequestBoundPaymentService(request).create_checkout_session(
            request.user,
            CheckoutPlan(
                plan=plan["plan"],
                price_cents=plan["price_cents"],
                currency=plan["currency"],
                recurring=plan["recurring"],
                reference=reference,
            ),
            provider=selected,
        )
    except Exception as exc:
        result = {"url": "", "error": "Payment provider is temporarily unavailable.", "error_classification": "unknown provider failure"}
        invoice.metadata = {
            **(invoice.metadata or {}),
            "state": "checkout_failed",
            "error": type(exc).__name__,
            "error_classification": "unknown provider failure",
        }
        invoice.save(update_fields=["metadata"])

    checkout_url = result.get("url") if isinstance(result, dict) else ""
    parsed_checkout_url = urlparse(str(checkout_url))
    if not isinstance(result, dict) or parsed_checkout_url.scheme not in {"http", "https"} or not parsed_checkout_url.netloc:
        error = result.get("error") if isinstance(result, dict) else "invalid_provider_response"
        classification = result.get("error_classification") if isinstance(result, dict) else "unknown provider failure"
        invoice.metadata = {
            **(invoice.metadata or {}),
            "state": "checkout_failed",
            "error": error or "provider_checkout_failed",
            "error_classification": classification,
        }
        invoice.save(update_fields=["metadata"])
        return None, "Payment provider could not start checkout. No subscription was activated. Please try again."

    external_id = result.get("invoice_id") or result.get("order_tracking_id") or result.get("session_id") or ""
    invoice.external_id = external_id or None
    invoice.metadata = {
        **(invoice.metadata or {}),
        "state": "checkout_open",
        "reference": result.get("reference") or reference,
        "tracking_id": result.get("order_tracking_id"),
        "session_id": result.get("session_id"),
        "subscription_id": result.get("subscription_id"),
        "provider_plan_id": result.get("provider_plan_id"),
        "provider_customer_id": result.get("provider_customer_id"),
        "error": "",
        "error_classification": "",
    }
    try:
        invoice.save(update_fields=["external_id", "metadata"])
    except IntegrityError:
        invoice.external_id = None
        invoice.metadata = {
            **(invoice.metadata or {}),
            "state": "checkout_failed",
            "error": "duplicate_provider_reference",
            "error_classification": "provider rejected request",
        }
        invoice.save(update_fields=["external_id", "metadata"])
        return None, "Payment provider could not start checkout. No subscription was activated. Please try again."
    return checkout_url, None

@login_required
def billing_checkout_start(request):
    if request.method != "POST":
        return HttpResponseRedirect(reverse("billing_page"))
    url, error = _checkout(request, request.POST.get("plan", ""), request.POST.get("provider") or None)
    if url:
        return HttpResponseRedirect(url)
    messages.error(request, error or "Payment provider could not start checkout. No subscription was activated. Please try again.")
    return redirect("billing_page")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_plans(request): return Response({"plans": _plans(), "provider": str(getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_status(request):
    subscription, _ = Subscription.objects.get_or_create(user=request.user)
    snapshot = _subscription_snapshot(subscription)
    payments = []
    for payment in Payment.objects.filter(user=request.user, status__in=["PENDING", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED", "REFUNDED"]).select_related("invoice")[:10]:
        invoice_meta = payment.invoice.metadata if payment.invoice else {}
        safe_meta = {k: v for k, v in invoice_meta.items() if k not in {"checkout_url", "provider_payload", "provider_status"}}
        payments.append({"id": payment.id, "external_id": payment.external_id, "amount_cents": payment.amount_cents, "currency": payment.currency, "status": payment.status, "created_at": payment.created_at, "invoice_id": payment.invoice_id, "metadata": safe_meta})
    invoices = []
    for item in Invoice.objects.filter(user=request.user, paid=True)[:10]:
        safe_meta = {k: v for k, v in (item.metadata or {}).items() if k not in {"checkout_url", "provider_payload", "provider_status"}}
        invoices.append({"id": item.id, "external_id": item.external_id, "amount_cents": item.amount_cents, "currency": item.currency, "paid": item.paid, "metadata": safe_meta, "created_at": item.created_at})
    return Response({"subscription": snapshot, "invoices": invoices, "payments": payments, "plans": _plans()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_checkout(request):
    plan_name = str(request.data.get("plan") or "").upper().strip()
    url, error = _checkout(request, plan_name, request.data.get("provider"))
    if error: return Response({"detail": error}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"url": url, "plan": plan_name, "payment_required": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_change_plan(request):
    requested = str(request.data.get("plan") or "").upper().strip()
    plan = _plan(requested)
    if not plan: return Response({"detail": "Unknown subscription plan."}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        subscription, _ = Subscription.objects.select_for_update().get_or_create(user=request.user)
        current_active = subscription.is_active and (not subscription.expires_at or subscription.expires_at > timezone.now())
        if subscription.plan == plan["plan"] and current_active:
            return Response({"changed": False, "plan": subscription.plan, "detail": "This is already the active plan."})
        if plan["plan"] == "FREE":
            subscription.plan = "FREE"
            subscription.price_cents = 0
            subscription.currency = plan["currency"].lower()
            subscription.recurring = False
            subscription.is_active = True
            subscription.expires_at = None
            subscription.renewed_at = timezone.now()
            subscription.save(update_fields=["plan", "price_cents", "currency", "recurring", "is_active", "expires_at", "renewed_at"])
            return Response({"changed": True, "plan": "FREE", "status": "active", "payment_required": False})
    url, error = _checkout(request, requested, request.data.get("provider"))
    if error: return Response({"detail": error}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"url": url, "plan": requested, "payment_required": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_reconcile(request):
    invoice = Invoice.objects.filter(user=request.user, pk=request.data.get("invoice_id")).first()
    if not invoice: return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
    provider = str((invoice.metadata or {}).get("provider") or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()
    result = _reconcile_invoice(invoice, provider)
    if result["state"] == "INVALID_PLAN": return Response({"detail": "The invoice is not associated with a configured plan."}, status=status.HTTP_409_CONFLICT)
    if result["state"] == "UNSUPPORTED_PROVIDER": return Response({"detail": "Unsupported payment provider."}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"paid": result["paid"], "state": result["state"], "invoice_id": invoice.id, "subscription": getattr(result.get("subscription"), "plan", Subscription.objects.get(user=request.user).plan)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_cancel(request):
    """Stop future renewal while preserving access through the paid cycle."""
    with transaction.atomic():
        subscription, _ = Subscription.objects.select_for_update().get_or_create(user=request.user)
        if subscription.plan == "FREE":
            return Response({"status": "already_free", "plan": "FREE", "expires_at": None})
        if not subscription.is_active:
            return Response({"status": "already_cancelled", "plan": subscription.plan, "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None})
        subscription.recurring = False
        if not subscription.expires_at:
            subscription.expires_at = timezone.now() + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30)))
        subscription.cancelled_at = timezone.now()
        subscription.cancellation_reason = "user_requested"
        subscription.save(update_fields=["recurring", "expires_at", "cancelled_at", "cancellation_reason"])
        return Response({"status": "cancelled_at_period_end", "plan": subscription.plan, "expires_at": subscription.expires_at.isoformat()})
