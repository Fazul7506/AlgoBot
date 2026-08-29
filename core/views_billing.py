"""Authenticated billing API and provider checkout callback pages."""
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Invoice, Payment, Subscription
from core.services.payment_service import PaymentService


@dataclass(frozen=True)
class CheckoutPlan:
    plan: str
    price_cents: int
    currency: str = "KES"
    recurring: bool = True


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
    configured = {
        "BASIC": _safe_price(getattr(settings, "ALGOBOT_BASIC_PRICE_CENTS", None)),
        "PRO": _safe_price(getattr(settings, "ALGOBOT_PRO_PRICE_CENTS", None)),
        "ENTERPRISE": _safe_price(getattr(settings, "ALGOBOT_ENTERPRISE_PRICE_CENTS", None)),
    }
    plans = [{"plan": "FREE", "price_cents": 0, "currency": currency, "recurring": False, "configured": True}]
    for name, price in configured.items():
        plans.append({"plan": name, "price_cents": price, "currency": currency, "recurring": True, "configured": price is not None and price >= 0})
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
    return {
        "plan": subscription.plan,
        "price_cents": subscription.price_cents,
        "currency": subscription.currency,
        "is_active": bool(subscription.is_active and not expired),
        "recurring": bool(subscription.recurring and subscription.is_active and not expired),
        "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
    }


def _activate(invoice, plan):
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        subscription, _ = Subscription.objects.select_for_update().get_or_create(user=invoice.user)
        renewed_at = timezone.now()
        subscription.plan = plan["plan"]
        subscription.price_cents = int(plan["price_cents"])
        subscription.currency = plan["currency"].lower()
        subscription.recurring = bool(plan["recurring"])
        subscription.is_active = True
        subscription.renewed_at = renewed_at
        subscription.expires_at = renewed_at + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30))) if subscription.recurring else None
        subscription.save(update_fields=["plan", "price_cents", "currency", "recurring", "is_active", "renewed_at", "expires_at"])
        invoice.paid = True
        invoice.metadata = {**(invoice.metadata or {}), "subscription_activated": True, "plan": plan["plan"]}
        invoice.save(update_fields=["paid", "metadata"])
        Payment.objects.filter(invoice=invoice).update(status="COMPLETED")
        return invoice, subscription


def _provider_state(result, provider):
    data = result or {}
    if provider == PaymentService.INTASEND and isinstance(data.get("invoice"), dict):
        data = {**data, **data["invoice"]}
    if provider == PaymentService.PESAPAL:
        return str(data.get("payment_status_description", "")).upper(), data
    return str(data.get("state", "")).upper(), data


def _persist_callback_payment(invoice, state, payload=None):
    state = str(state or "").upper()
    normalized = "COMPLETED" if state in {"COMPLETE", "COMPLETED", "COMPLETED_SUCCESS", "SUCCESS", "SUCCEEDED", "PAID"} else "FAILED" if state in {"FAILED", "FAILURE", "CANCELLED", "CANCELED", "INVALID", "REVERSED"} else "PENDING"
    payload = payload or {}
    external_id = invoice.external_id or payload.get("order_tracking_id") or payload.get("invoice_id")
    payment = Payment.objects.filter(invoice=invoice).order_by("-created_at").first()
    if payment is None:
        payment = Payment.objects.create(user=invoice.user, invoice=invoice, external_id=external_id or None, amount_cents=invoice.amount_cents, currency=invoice.currency, status=normalized)
    else:
        payment.external_id = external_id or payment.external_id
        payment.amount_cents = invoice.amount_cents
        payment.currency = invoice.currency
        payment.status = normalized
        payment.save(update_fields=["external_id", "amount_cents", "currency", "status"])
    return payment


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
        result = service.get_intasend_payment_status(invoice.external_id) if invoice.external_id else None
    else:
        return {"paid": False, "state": "UNSUPPORTED_PROVIDER", "invoice": invoice, "subscription": None}
    state, payload = _provider_state(result, provider)
    success_states = {"COMPLETE", "COMPLETED", "COMPLETED_SUCCESS", "SUCCESS", "SUCCEEDED", "PAID"}
    failed_states = {"FAILED", "FAILURE", "CANCELLED", "CANCELED", "INVALID", "REVERSED"}
    if state in success_states:
        invoice, subscription = _activate(invoice, plan)
        _persist_callback_payment(invoice, state, payload)
        return {"paid": True, "state": "COMPLETE", "invoice": invoice, "subscription": subscription, "provider_payload": payload}
    if state in failed_states:
        _persist_callback_payment(invoice, state, payload)
        return {"paid": False, "state": "FAILED", "invoice": invoice, "subscription": Subscription.objects.filter(user=invoice.user).first(), "provider_payload": payload}
    _persist_callback_payment(invoice, state or "PENDING", payload)
    return {"paid": False, "state": "PENDING", "invoice": invoice, "subscription": Subscription.objects.filter(user=invoice.user).first(), "provider_payload": payload}


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
    tracking_id = str(request.GET.get("tracking_id") or request.GET.get("OrderTrackingId") or "").strip()
    invoice = _find_callback_invoice(request, reference, tracking_id)
    result = None
    if invoice and provider:
        try:
            result = _reconcile_invoice(invoice, provider)
        except Exception:
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
    invoice = Invoice.objects.create(user=request.user, amount_cents=plan["price_cents"], currency=plan["currency"], metadata={"plan": plan["plan"], "provider": selected, "state": "checkout_created"})
    result = RequestBoundPaymentService(request).create_checkout_session(request.user, CheckoutPlan(plan=plan["plan"], price_cents=plan["price_cents"], currency=plan["currency"], recurring=plan["recurring"]), provider=selected)
    if not result.get("url"):
        invoice.metadata = {**(invoice.metadata or {}), "state": "checkout_failed", "error": result.get("error") or "provider_checkout_failed"}
        invoice.save(update_fields=["metadata"])
        return None, "We couldn't start your payment. Please try again."
    external_id = result.get("invoice_id") or result.get("order_tracking_id") or result.get("session_id") or ""
    invoice.external_id = external_id or None
    invoice.metadata = {**(invoice.metadata or {}), "state": "checkout_open", "reference": result.get("reference"), "tracking_id": result.get("order_tracking_id"), "session_id": result.get("session_id")}
    invoice.save(update_fields=["external_id", "metadata"])
    return result["url"], None


@login_required
def billing_checkout_start(request):
    if request.method != "GET":
        return redirect("billing_page")
    url, error = _checkout(request, request.GET.get("plan", ""), request.GET.get("provider") or None)
    if url:
        return HttpResponseRedirect(url)
    messages.error(request, error or "We couldn't start your payment. Please try again.")
    return redirect("billing_page")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_plans(request):
    return Response({"plans": _plans(), "provider": str(getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_status(request):
    subscription, _ = Subscription.objects.get_or_create(user=request.user)
    snapshot = _subscription_snapshot(subscription)
    payments = []
    for payment in Payment.objects.filter(user=request.user, status__in=["PENDING", "COMPLETED", "FAILED"]).select_related("invoice")[:10]:
        invoice_meta = payment.invoice.metadata if payment.invoice else {}
        payments.append({"id": payment.id, "external_id": payment.external_id, "amount_cents": payment.amount_cents, "currency": payment.currency, "status": payment.status, "created_at": payment.created_at, "invoice_id": payment.invoice_id, "metadata": invoice_meta or {}})
    invoices = list(Invoice.objects.filter(user=request.user, paid=True)[:10].values("id", "external_id", "amount_cents", "currency", "paid", "metadata", "created_at"))
    return Response({"subscription": snapshot, "invoices": invoices, "payments": payments, "plans": _plans()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_checkout(request):
    plan_name = str(request.data.get("plan") or "").upper().strip()
    url, error = _checkout(request, plan_name, request.data.get("provider"))
    if error:
        return Response({"detail": error}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"url": url, "plan": plan_name, "payment_required": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_change_plan(request):
    requested = str(request.data.get("plan") or "").upper().strip()
    plan = _plan(requested)
    if not plan:
        return Response({"detail": "Unknown subscription plan."}, status=status.HTTP_400_BAD_REQUEST)
    subscription, _ = Subscription.objects.get_or_create(user=request.user)
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
    if error:
        return Response({"detail": error}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"url": url, "plan": requested, "payment_required": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_reconcile(request):
    invoice = Invoice.objects.filter(user=request.user, pk=request.data.get("invoice_id")).first()
    if not invoice:
        return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
    provider = str((invoice.metadata or {}).get("provider") or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()
    result = _reconcile_invoice(invoice, provider)
    if result["state"] == "INVALID_PLAN":
        return Response({"detail": "The invoice is not associated with a configured plan."}, status=status.HTTP_409_CONFLICT)
    if result["state"] == "UNSUPPORTED_PROVIDER":
        return Response({"detail": "Unsupported payment provider."}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"paid": result["paid"], "state": result["state"], "invoice_id": invoice.id, "subscription": getattr(result.get("subscription"), "plan", Subscription.objects.get(user=request.user).plan)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_cancel(request):
    """Stop future renewal while preserving access through the paid cycle."""
    subscription, _ = Subscription.objects.get_or_create(user=request.user)
    if subscription.plan == "FREE":
        return Response({"status": "already_free", "plan": "FREE", "expires_at": None})
    if not subscription.is_active:
        return Response({"status": "already_cancelled", "plan": subscription.plan, "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None})
    subscription.recurring = False
    if not subscription.expires_at:
        subscription.expires_at = timezone.now() + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30)))
    subscription.save(update_fields=["recurring", "expires_at"])
    return Response({"status": "cancelled_at_period_end", "plan": subscription.plan, "expires_at": subscription.expires_at.isoformat()})
