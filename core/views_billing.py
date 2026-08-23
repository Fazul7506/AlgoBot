"""Authenticated billing API: plan discovery, checkout, reconciliation and cancellation."""
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
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


def _plans():
    plans = [{"plan": "FREE", "price_cents": 0, "currency": "KES", "recurring": False}]
    configured = {"BASIC": getattr(settings, "ALGOBOT_BASIC_PRICE_CENTS", None), "PRO": getattr(settings, "ALGOBOT_PRO_PRICE_CENTS", None), "ENTERPRISE": getattr(settings, "ALGOBOT_ENTERPRISE_PRICE_CENTS", None)}
    currency = str(getattr(settings, "ALGOBOT_BILLING_CURRENCY", "KES")).upper()
    for name, price in configured.items():
        if price not in (None, ""):
            plans.append({"plan": name, "price_cents": int(price), "currency": currency, "recurring": True})
    return plans


def _plan(name): return next((item for item in _plans() if item["plan"] == str(name).upper()), None)


def _activate(invoice, plan):
    subscription, _ = Subscription.objects.get_or_create(user=invoice.user)
    subscription.plan = plan["plan"]; subscription.price_cents = int(plan["price_cents"]); subscription.currency = plan["currency"].lower(); subscription.recurring = bool(plan["recurring"]); subscription.is_active = True; subscription.renewed_at = timezone.now()
    subscription.expires_at = timezone.now() + timedelta(days=int(getattr(settings, "ALGOBOT_SUBSCRIPTION_PERIOD_DAYS", 30))) if plan["recurring"] else None
    subscription.save()
    invoice.paid = True; invoice.metadata = {**(invoice.metadata or {}), "subscription_activated": True, "plan": plan["plan"]}; invoice.save(update_fields=["paid", "metadata"])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_plans(request): return Response({"plans": _plans(), "provider": str(getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def billing_status(request):
    subscription, _ = Subscription.objects.get_or_create(user=request.user)
    invoices = list(Invoice.objects.filter(user=request.user)[:10].values("id", "external_id", "amount_cents", "currency", "paid", "metadata", "created_at"))
    payments = list(Payment.objects.filter(user=request.user)[:10].values("id", "external_id", "amount_cents", "currency", "status", "created_at"))
    return Response({"subscription": {"plan": subscription.plan, "price_cents": subscription.price_cents, "currency": subscription.currency, "is_active": subscription.is_active, "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None}, "invoices": invoices, "payments": payments})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_checkout(request):
    plan = _plan(request.data.get("plan"))
    if not plan or plan["plan"] == "FREE": return Response({"detail": "Select a configured paid subscription plan."}, status=status.HTTP_400_BAD_REQUEST)
    provider = str(request.data.get("provider") or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower()
    invoice = Invoice.objects.create(user=request.user, amount_cents=plan["price_cents"], currency=plan["currency"], metadata={"plan": plan["plan"], "provider": provider, "state": "checkout_created"})
    result = PaymentService().create_checkout_session(request.user, CheckoutPlan(**plan), provider=provider)
    if not result.get("url"):
        invoice.metadata = {**invoice.metadata, "state": "checkout_failed", "error": result.get("error", "Unable to create checkout")}; invoice.save(update_fields=["metadata"])
        return Response(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    external_id = result.get("invoice_id") or result.get("order_tracking_id") or result.get("session_id") or ""
    invoice.external_id = external_id; invoice.metadata = {**invoice.metadata, "state": "checkout_open", "reference": result.get("reference"), "tracking_id": result.get("order_tracking_id"), "session_id": result.get("session_id")}; invoice.save(update_fields=["external_id", "metadata"])
    Payment.objects.create(user=request.user, invoice=invoice, external_id=external_id, amount_cents=plan["price_cents"], currency=plan["currency"], status="pending")
    return Response({**result, "plan": plan["plan"], "invoice_id": invoice.id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_reconcile(request):
    invoice = Invoice.objects.filter(user=request.user, pk=request.data.get("invoice_id")).first()
    if not invoice: return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
    plan = _plan((invoice.metadata or {}).get("plan"))
    if not plan: return Response({"detail": "The invoice is not associated with a configured plan."}, status=status.HTTP_409_CONFLICT)
    provider = str((invoice.metadata or {}).get("provider") or getattr(settings, "PAYMENT_PROVIDER", "intasend")).lower(); service = PaymentService()
    if provider == service.PESAPAL:
        tracking = (invoice.metadata or {}).get("tracking_id") or invoice.external_id; result = service.get_pesapal_transaction_status(str(tracking)) if tracking else None; state = str((result or {}).get("payment_status_description", "")).upper(); paid = state in {"COMPLETED", "COMPLETED_SUCCESS", "SUCCESS"}
    elif provider == service.INTASEND:
        result = service.get_intasend_payment_status(invoice.external_id) if invoice.external_id else None; state = str((result or {}).get("state", "")).upper(); paid = state == "COMPLETE"
    else: return Response({"detail": "Unsupported payment provider."}, status=status.HTTP_400_BAD_REQUEST)
    if paid: _activate(invoice, plan); Payment.objects.filter(invoice=invoice).update(status="complete")
    elif state in {"FAILED", "CANCELLED", "INVALID"}: Payment.objects.filter(invoice=invoice).update(status=state.lower())
    return Response({"paid": paid, "state": state or "PENDING", "invoice_id": invoice.id, "subscription": Subscription.objects.get(user=request.user).plan})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_cancel(request):
    subscription, _ = Subscription.objects.get_or_create(user=request.user); subscription.is_active = False; subscription.expires_at = timezone.now(); subscription.save(update_fields=["is_active", "expires_at"])
    return Response({"status": "cancelled", "plan": subscription.plan, "expires_at": subscription.expires_at.isoformat()})
