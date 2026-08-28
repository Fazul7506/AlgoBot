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
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def pesapal_webhook(request):
    payload = request.body if request.method == "POST" else request.GET.dict()
    result = PaymentReconciler.handle_pesapal_webhook(payload)
    ack = (result or {}).get("ipn_ack") if result else None
    if ack:
        return JsonResponse(ack)
    return HttpResponse(status=400)


@require_http_methods(["GET"])
def pesapal_callback(request):
    tracking_id = request.GET.get("OrderTrackingId", "")
    merchant_reference = request.GET.get("OrderMerchantReference", "")
    result = PaymentReconciler.handle_pesapal_callback(tracking_id, merchant_reference)
    status = (result or {}).get("status", "PENDING")
    return redirect(
        f"/billing/success/?provider=pesapal&reference={merchant_reference}&tracking_id={tracking_id}&status={status}"
    )
