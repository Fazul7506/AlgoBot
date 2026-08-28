"""Billing views.

The browser checkout is deliberately separate from the JSON API. A trader
clicking Upgrade is sent directly to the hosted payment page; provider JSON
is never rendered as a browser confirmation dialog.
"""
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
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
    """Payment service whose callback URL is tied to the real public request."""
    def __init__(self, request):
        self._request = request
        super().__init__()

    def _base_url(self):
        configured = str(getattr(settings, "BASE_URL", "") or "").split(",")[0].strip().rstrip("/")
        parsed = urlparse(configured)
        host = self._request.get_host().split(":", 1)[0]
        local_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        if parsed.scheme == "https" and parsed.netloc:
            configured_host = parsed.hostname or ""
            if configured_host.lower() not in local_hosts:
                return configured
        scheme = "https" if not settings.DEBUG else self._request.scheme
        return f"{scheme}://{host}".rstrip("/")


def _plans():
    currency = str(getattr(settings, "ALGOBOT_BILLING_CURRENCY", "KES")).upper()
    configured = {
        "BASIC": getattr(settings, "ALGOBOT_BASIC_PRICE_CENTS", None),
        "PRO": getattr(settings, "ALGOBOT_PRO_PRICE_CENTS", None),
        "ENTERPRISE": getattr(settings, "ALGOBOT_ENTERPRISE_PRICE_CENTS", None),
    }
    plans = [{"plan": "FREE", "price_cents": 0, "currency": currency, "recurring": False, "configured": True}]
    for name, price in configured.items():
        ok = price not in (None, "")
        plans.append({"plan": name, "price_cents": int(price) if ok else None, "currency": currency, "recurring": True, "configured": ok})
    return plans


def _plan(name):
    return next((item for item in _plans() if item["plan"] == str(name).upper().strip()), None)


def _activate(invoice, plan):
    subscription, _ = Subscription.objects.get_or_create(user=invoice.user)
    subscription.plan = plan["plan"]
    subscription.price_cents = int(plan["price_cents"])
    subscription.currency = plan["currency"].lower()
    subscription.recurring = bool(plan["recurring"])
    subscription.is_active = True
    subscription.renewed_at = timezone.now()
    subscription.expires_at = timezone.now() + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30))) if plan["recurring"] else None
    subscription.save()
    invoice.paid = True
    invoice.metadata = {**(invoice.metadata or {}), "subscription_activated": True, "plan": plan["plan"]}
    invoice.save(update_fields=["paid", "metadata"])


def _checkout(request, plan_name, provider=None):
    plan = _plan(plan_name)
    if not plan:
        return None, "Unknown subscription plan."
    if plan["plan"] == "FREE":
        return None, "FREE does not require payment."
    if not plan["configured"]:
        return None, f"{plan['plan']} is not configured for checkout yet."
    selected = str(provider or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower().strip()
    invoice = Invoice.objects.create(user=request.user, amount_cents=plan["price_cents"], currency=plan["currency"], metadata={"plan": plan["plan"], "provider": selected, "state": "checkout_created"})
    result = RequestBoundPaymentService(request).create_checkout_session(request.user, CheckoutPlan(**{k: plan[k] for k in ("plan", "price_cents", "currency", "recurring")}), provider=selected)
    if not result.get("url"):
        invoice.metadata = {**(invoice.metadata or {}), "state": "checkout_failed", "error": "provider_checkout_failed"}
        invoice.save(update_fields=["metadata"])
        return None, "We couldn't start your payment. Please try again."
    external_id = result.get("invoice_id") or result.get("order_tracking_id") or result.get("session_id") or ""
    invoice.external_id = external_id or None
    invoice.metadata = {**(invoice.metadata or {}), "state": "checkout_open", "reference": result.get("reference"), "tracking_id": result.get("order_tracking_id"), "session_id": result.get("session_id")}
    invoice.save(update_fields=["external_id", "metadata"])
    Payment.objects.create(user=request.user, invoice=invoice, external_id=external_id or None, amount_cents=plan["price_cents"], currency=plan["currency"], status="PENDING")
    return result["url"], None


@login_required
def billing_checkout_start(request):
    if request.method != "GET":
        return redirect("billing_page")
    plan = request.GET.get("plan", "")
    provider = request.GET.get("provider") or None
    url, error = _checkout(request, plan, provider)
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
    invoices = list(Invoice.objects.filter(user=request.user)[:10].values("id", "external_id", "amount_cents", "currency", "paid", "metadata", "created_at"))
    payments = list(Payment.objects.filter(user=request.user)[:10].values("id", "external_id", "amount_cents", "currency", "status", "created_at", "invoice_id"))
    return Response({"subscription": {"plan": subscription.plan, "price_cents": subscription.price_cents, "currency": subscription.currency, "is_active": subscription.is_active, "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None}, "invoices": invoices, "payments": payments, "plans": _plans()})


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
    if subscription.plan == plan["plan"] and subscription.is_active:
        return Response({"changed": False, "plan": subscription.plan, "detail": "This is already the active plan."})
    if plan["plan"] == "FREE":
        subscription.plan = "FREE"; subscription.price_cents = 0; subscription.currency = plan["currency"].lower(); subscription.recurring = False; subscription.is_active = True; subscription.expires_at = None; subscription.renewed_at = timezone.now()
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
    plan = _plan((invoice.metadata or {}).get("plan"))
    if not plan:
        return Response({"detail": "The invoice is not associated with a configured plan."}, status=status.HTTP_409_CONFLICT)
    provider = str((invoice.metadata or {}).get("provider") or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()
    service = PaymentService()
    if provider == service.PESAPAL:
        tracking = (invoice.metadata or {}).get("tracking_id") or invoice.external_id
        result = service.get_pesapal_transaction_status(str(tracking)) if tracking else None
        state = str((result or {}).get("payment_status_description", "")).upper()
        paid = state in {"COMPLETED", "COMPLETED_SUCCESS", "SUCCESS", "SUCCEEDED", "PAID"}
    elif provider == service.INTASEND:
        result = service.get_intasend_payment_status(invoice.external_id) if invoice.external_id else None
        state = str((result or {}).get("state", "")).upper()
        paid = state in {"COMPLETE", "COMPLETED", "SUCCESS", "SUCCEEDED", "PAID"}
    else:
        return Response({"detail": "Unsupported payment provider."}, status=status.HTTP_400_BAD_REQUEST)
    if paid:
        _activate(invoice, plan); Payment.objects.filter(invoice=invoice).update(status="COMPLETED")
    elif state in {"FAILED", "CANCELLED", "CANCELED", "INVALID", "REVERSED"}:
        Payment.objects.filter(invoice=invoice).update(status="FAILED")
    return Response({"paid": paid, "state": state or "PENDING", "invoice_id": invoice.id, "subscription": Subscription.objects.get(user=request.user).plan})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_cancel(request):
    subscription, _ = Subscription.objects.get_or_create(user=request.user)
    subscription.is_active = False; subscription.expires_at = timezone.now()
    subscription.save(update_fields=["is_active", "expires_at"])
    return Response({"status": "cancelled", "plan": subscription.plan, "expires_at": subscription.expires_at.isoformat()})
