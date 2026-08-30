from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .telegram_runtime import telegram_health


@login_required
@require_GET
def telegram_health_view(request):
    health = telegram_health()
    status_code = 200 if health.get("status") == "healthy" else 503
    return JsonResponse(health, status=status_code)
