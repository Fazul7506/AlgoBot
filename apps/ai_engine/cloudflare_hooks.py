from __future__ import annotations

import hmac
import json
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def cloudflare_training_dispatch(request):
    """Authenticated Cloudflare Queue webhook; enqueue work on the existing Celery runtime."""
    expected = os.environ.get("CLOUDFLARE_TRAINING_WEBHOOK_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
        return JsonResponse({"status": "unauthorized"}, status=401)
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"status": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"status": "invalid_payload"}, status=400)
    timeframe = str(payload.get("timeframe", "M1"))
    try:
        min_accuracy = float(payload.get("min_accuracy", 0.52))
    except (TypeError, ValueError):
        return JsonResponse({"status": "invalid_min_accuracy"}, status=400)
    if not 0.0 <= min_accuracy <= 1.0:
        return JsonResponse({"status": "invalid_min_accuracy"}, status=400)
    if timeframe not in {"M1", "M2", "M5", "M10", "M15", "M30", "H1", "H4", "D1", "1m", "2m", "5m", "10m", "15m", "30m", "1h", "4h", "1d"}:
        return JsonResponse({"status": "unsupported_timeframe"}, status=400)

    from apps.ai_engine.tasks import scheduled_ai_training
    task = scheduled_ai_training.apply_async(
        kwargs={"timeframe": timeframe, "min_accuracy": min_accuracy},
        queue="celery",
    )
    return JsonResponse({"status": "queued", "task_id": task.id}, status=202)
