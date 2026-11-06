from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from core.services.payment_reconciler import PaymentReconciler


@csrf_exempt
@require_http_methods(["POST"])
def intasend_webhook(request):
    result = PaymentReconciler.handle_intasend_webhook(request.body)
    if result is None:
        return HttpResponse(status=400)
    if result.get("retryable"):
        return HttpResponse(status=500)
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def pesapal_webhook(request):
    payload = request.body if request.method == "POST" else request.GET.dict()
    result = PaymentReconciler.handle_pesapal_webhook(payload)
    if not (request.GET.get("OrderTrackingId") or request.POST.get("OrderTrackingId") or request.GET.get("orderTrackingId") or request.POST.get("orderTrackingId")):
        return HttpResponse(status=400)
    if result and result.get("retryable"):
        return HttpResponse(status=500)
    ack = (result or {}).get("ipn_ack") if result else None
    if ack:
        return JsonResponse(ack)
    # A provider-status lookup failure is retryable; malformed notifications are not.
    return HttpResponse(status=500)


@require_http_methods(["GET"])
def pesapal_callback(request):
    tracking_id = request.GET.get("OrderTrackingId", "")
    merchant_reference = request.GET.get("OrderMerchantReference", "")
    result = PaymentReconciler.handle_pesapal_callback(tracking_id, merchant_reference)
    status = (result or {}).get("status", "PENDING")
    return redirect(
        f"/billing/success/?provider=pesapal&reference={merchant_reference}&tracking_id={tracking_id}&status={status}"
    )


@csrf_exempt
@require_http_methods(["POST"])
def paypal_webhook(request):
    from core.services.payment_service import PaymentService
    import json
    try:
        event = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)
    service = PaymentService()
    if not service.verify_paypal_webhook(request.headers, event):
        return HttpResponse(status=400)
    result = PaymentReconciler.handle_paypal_webhook(event)
    if result is None or result.get("retryable"):
        return HttpResponse(status=500)
    return HttpResponse(status=200)


@require_http_methods(["GET"])
def paypal_return(request):
    from core.services.payment_service import PaymentService
    order_id = str(request.GET.get("token") or request.GET.get("order_id") or "").strip()
    result = PaymentService().capture_paypal_order(order_id)
    invoice = result.get("invoice") if isinstance(result, dict) else None
    if invoice:
        reference = str((invoice.metadata or {}).get("reference") or "")
        return redirect(f"/billing/success/?provider=paypal&reference={reference}&tracking_id={invoice.external_id or ''}")
    return redirect("/billing/cancel/?provider=paypal&status=payment_pending")
