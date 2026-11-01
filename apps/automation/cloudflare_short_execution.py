"""Strictly bounded short-operation webhook prototype.

This endpoint intentionally does not execute arbitrary Celery task names. Heavy
Django/ML work remains on the existing Celery path until a separate execution
runtime is validated.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL_SECONDS = 600
MAX_BODY_BYTES = 4096
MAX_EXECUTION_SECONDS = 1.0
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _health_check(params: dict) -> dict:
    """A deliberately side-effect-free, bounded prototype operation."""
    if params:
        raise ValueError("health_check accepts no parameters")
    return {"healthy": True}


# The values are local handlers, never import paths supplied by the caller.
ALLOWED_SHORT_OPERATIONS = {
    "health_check": _health_check,
}


@csrf_exempt
@require_POST
def cloudflare_short_execution(request):
    """Authenticate and run only explicitly allowlisted, bounded operations."""
    if os.environ.get("CLOUDFLARE_SHORT_EXECUTION_ACTIVE", "").lower() != "true":
        return JsonResponse({"status": "disabled"}, status=503)

    expected = os.environ.get("CLOUDFLARE_SHORT_EXECUTION_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
        return JsonResponse({"status": "unauthorized"}, status=401)

    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({"status": "payload_too_large"}, status=413)
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"status": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"status": "invalid_payload"}, status=400)

    request_id = payload.get("request_id")
    operation = payload.get("operation")
    params = payload.get("params", {})
    if (
        not isinstance(request_id, str)
        or not REQUEST_ID_RE.fullmatch(request_id)
        or not isinstance(operation, str)
        or operation not in ALLOWED_SHORT_OPERATIONS
        or not isinstance(params, dict)
    ):
        logger.warning("Rejected invalid Cloudflare short-operation request")
        return JsonResponse({"status": "invalid_payload"}, status=400)

    key_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    request_fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    idempotency_key = f"cf-short-op:{key_digest}"
    in_progress = {
        "status": "running",
        "operation": operation,
        "fingerprint": request_fingerprint,
    }
    if not cache.add(idempotency_key, in_progress, timeout=IDEMPOTENCY_TTL_SECONDS):
        existing = cache.get(idempotency_key)
        if not isinstance(existing, dict) or existing.get("fingerprint") != request_fingerprint:
            return JsonResponse({"status": "idempotency_key_conflict"}, status=409)
        if existing.get("status") == "completed":
            return JsonResponse({
                "status": "duplicate",
                "request_id": request_id,
                "result": existing.get("result"),
            }, status=200)
        return JsonResponse({"status": "already_processing", "request_id": request_id}, status=202)

    started = time.monotonic()
    try:
        result = ALLOWED_SHORT_OPERATIONS[operation](params)
        elapsed = time.monotonic() - started
        if elapsed > MAX_EXECUTION_SECONDS:
            # This detects an overrun but cannot pre-empt Python execution. The
            # allowlist must therefore remain limited to intrinsically bounded code.
            cache.delete(idempotency_key)
            logger.error("Short operation exceeded execution budget: %s", operation)
            return JsonResponse({"status": "execution_budget_exceeded"}, status=503)
        cache.set(
            idempotency_key,
            {
                "status": "completed",
                "operation": operation,
                "fingerprint": request_fingerprint,
                "result": result,
            },
            timeout=IDEMPOTENCY_TTL_SECONDS,
        )
        return JsonResponse({"status": "executed", "request_id": request_id, "result": result})
    except ValueError as exc:
        cache.delete(idempotency_key)
        return JsonResponse({"status": "invalid_parameters", "detail": str(exc)[:160]}, status=422)
    except Exception:
        cache.delete(idempotency_key)
        logger.exception("Cloudflare short operation failed: %s", operation)
        return JsonResponse({"status": "execution_failed"}, status=500)
