from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.utils.decorators import method_decorator

from core.services.payment_service import PaymentService

@method_decorator(csrf_exempt, name='dispatch')
def stripe_webhook(request):
    # Raw body and signature header
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    svc = PaymentService()
    result = svc.handle_webhook(payload, sig_header)

    if result is None:
        return HttpResponse(status=400)

    return JsonResponse(result)
