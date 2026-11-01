from __future__ import annotations

import hashlib
import hmac
import json
import os

from celery import current_app
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


# Deliberately allowlisted: never accept arbitrary task names from a public webhook.
ALLOWED_TASKS = {
    "apps.automation.tasks.process_due_scheduled_tasks": {"limit"},
    "apps.execution.process_execution_queue": {"batch_size"},
    "apps.ai_engine.tasks.check_ai_data_health": {"timeframe"},
    "apps.ai_engine.tasks.resolve_prediction_outcomes": {
        "timeframe", "horizon_candles", "batch_size"
    },
    "apps.notifications.tasks.telegram_watchdog": set(),
    "apps.notifications.tasks.recover_stuck_notifications": set(),
}
ALLOWED_SCHEDULES = {
    "automation-due-schedules-every-30-seconds": "apps.automation.tasks.process_due_scheduled_tasks",
    "execution-queue-recovery-every-30-seconds": "apps.execution.process_execution_queue",
    "ai-data-health-every-15-minutes": "apps.ai_engine.tasks.check_ai_data_health",
    "ai-resolve-predictions-every-5-minutes": "apps.ai_engine.tasks.resolve_prediction_outcomes",
    "telegram-watchdog-every-minute": "apps.notifications.tasks.telegram_watchdog",
    "telegram-recover-stuck-every-5-minutes": "apps.notifications.tasks.recover_stuck_notifications",
}
ALLOWED_TIMEFRAMES = {
    "M1", "M2", "M5", "M10", "M15", "M30", "H1", "H4", "D1",
    "1m", "2m", "5m", "10m", "15m", "30m", "1h", "4h", "1d",
}
IDEMPOTENCY_TTL_SECONDS = 180


def _validate_kwargs(task_name: str, kwargs: object) -> dict | None:
    if not isinstance(kwargs, dict):
        return None
    allowed = ALLOWED_TASKS[task_name]
    if set(kwargs) - allowed:
        return None
    clean = dict(kwargs)
    if "limit" in clean and (not isinstance(clean["limit"], int) or not 1 <= clean["limit"] <= 100):
        return None
    if "batch_size" in clean and (
        not isinstance(clean["batch_size"], int) or not 1 <= clean["batch_size"] <= 500
    ):
        return None
    if "horizon_candles" in clean and (
        not isinstance(clean["horizon_candles"], int) or not 1 <= clean["horizon_candles"] <= 100
    ):
        return None
    if "timeframe" in clean and clean["timeframe"] not in ALLOWED_TIMEFRAMES:
        return None
    return clean


@csrf_exempt
@require_POST
def cloudflare_task_dispatch(request):
    """Authenticate and enqueue a narrowly allowlisted scheduled Celery task."""
    expected = os.environ.get("CLOUDFLARE_TASK_DISPATCH_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
        return JsonResponse({"status": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"status": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"status": "invalid_payload"}, status=400)

    schedule_id = payload.get("schedule_id")
    task_name = payload.get("task")
    scheduled_minute = payload.get("scheduled_minute")
    if (
        not isinstance(schedule_id, str) or not schedule_id or len(schedule_id) > 100
        or task_name not in ALLOWED_TASKS
        or ALLOWED_SCHEDULES.get(schedule_id) != task_name
        or not isinstance(scheduled_minute, int) or scheduled_minute < 0
    ):
        return JsonResponse({"status": "invalid_payload"}, status=400)

    kwargs = _validate_kwargs(task_name, payload.get("kwargs", {}))
    if kwargs is None:
        return JsonResponse({"status": "invalid_kwargs"}, status=400)

    # The minute bucket deduplicates Cloudflare Queue redeliveries. The execution
    # task also retains its own distributed lock; this is not a substitute for it.
    raw_key = f"{schedule_id}:{task_name}:{scheduled_minute}"
    idempotency_key = "cf-task-dispatch:" + hashlib.sha256(raw_key.encode()).hexdigest()
    if not cache.add(idempotency_key, "dispatching", timeout=IDEMPOTENCY_TTL_SECONDS):
        return JsonResponse({"status": "duplicate", "schedule_id": schedule_id}, status=202)

    options = {"queue": "celery"}
    expires = payload.get("expires")
    if expires is not None:
        if not isinstance(expires, int) or not 1 <= expires <= 300:
            cache.delete(idempotency_key)
            return JsonResponse({"status": "invalid_expires"}, status=400)
        options["expires"] = expires

    try:
        result = current_app.send_task(task_name, kwargs=kwargs, **options)
    except Exception:
        # Allow the Queue delivery to retry if publishing to Celery failed.
        cache.delete(idempotency_key)
        return JsonResponse({"status": "dispatch_unavailable"}, status=503)

    cache.set(idempotency_key, result.id or "queued", timeout=IDEMPOTENCY_TTL_SECONDS)
    return JsonResponse(
        {"status": "queued", "schedule_id": schedule_id, "task": task_name, "task_id": result.id},
        status=202,
    )
