from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from core.services.payment_service import PaymentService


@csrf_exempt
@require_http_methods(["POST"])
def intasend_webhook(request):
    result = PaymentService().handle_webhook(request.body, request.META.get("HTTP_X_INTASEND_SIGNATURE", ""), provider="intasend")
    if result is None:
        return HttpResponse(status=400)
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def pesapal_webhook(request):
    if request.method == "POST":
        result = PaymentService().handle_webhook(request.body, provider="pesapal")
        ack = (result or {}).get("ipn_ack") if result else None
        if ack:
            return JsonResponse(ack)
        return HttpResponse(status=400)

    result = PaymentService().handle_webhook(request.GET.dict(), provider="pesapal")
    ack = (result or {}).get("ipn_ack") if result else None
    if ack:
        return JsonResponse(ack)
    return HttpResponse(status=400)


@require_http_methods(["GET"])
def pesapal_callback(request):
    tracking_id = request.GET.get("OrderTrackingId", "")
    merchant_reference = request.GET.get("OrderMerchantReference", "")
    result = PaymentService().handle_pesapal_callback(tracking_id, merchant_reference)
    status = (result or {}).get("status", "pending")
    return redirect(
        f"/billing/success/?provider=pesapal&reference={merchant_reference}&tracking_id={tracking_id}&status={status}"
    )
