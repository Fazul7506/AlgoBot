"""User-scoped trusted-browser management and security-alert feed."""
import hashlib
import json
import secrets

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from apps.observability.models import AuditEvent
from core.models import TrustedDevice

COOKIE_NAME = "algobot_trusted_device"
COOKIE_MAX_AGE = 60 * 60 * 24 * 180


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _json_body(request):
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


@login_required
@require_http_methods(["GET", "POST"])
def trusted_devices_api(request):
    if request.method == "GET":
        token = request.COOKIES.get(COOKIE_NAME, "")
        current_hash = _digest(token) if token else ""
        rows = list(TrustedDevice.objects.filter(user=request.user, revoked_at__isnull=True)[:100])
        current_row = next((row for row in rows if current_hash and secrets.compare_digest(row.token_hash, current_hash)), None)
        if current_row is not None:
            current_row.last_seen_at = timezone.now()
            current_row.save(update_fields=["last_seen_at"])
        return JsonResponse({"devices": [{
            "id": row.pk, "name": row.name, "created_at": row.created_at,
            "last_seen_at": row.last_seen_at, "current": bool(current_hash and secrets.compare_digest(row.token_hash, current_hash)),
        } for row in rows]})

    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Send a valid JSON object."}, status=400)
    password = payload.get("current_password", "")
    if not isinstance(password, str) or not request.user.check_password(password):
        return JsonResponse({"detail": "Confirm your current password to trust this browser."}, status=403)
    name = payload.get("name", "Trusted browser")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return JsonResponse({"detail": "Device name must be 1–100 characters."}, status=400)
    token = secrets.token_urlsafe(32)
    row = TrustedDevice.objects.create(user=request.user, name=name.strip(), token_hash=_digest(token), last_seen_at=timezone.now())
    response = JsonResponse({"ok": True, "device": {"id": row.pk, "name": row.name, "created_at": row.created_at}})
    response.set_cookie(COOKIE_NAME, token, max_age=COOKIE_MAX_AGE, httponly=True, secure=request.is_secure(), samesite="Lax", path="/")
    return response


@login_required
@require_http_methods(["DELETE"])
def trusted_device_detail_api(request, device_id):
    row = TrustedDevice.objects.filter(user=request.user, pk=device_id, revoked_at__isnull=True).first()
    if row is None:
        return JsonResponse({"detail": "Trusted device not found."}, status=404)
    row.revoked_at = timezone.now()
    row.save(update_fields=["revoked_at"])
    response = JsonResponse({"ok": True, "revoked": True})
    if request.COOKIES.get(COOKIE_NAME) and secrets.compare_digest(row.token_hash, _digest(request.COOKIES[COOKIE_NAME])):
        response.delete_cookie(COOKIE_NAME, path="/", samesite="Lax")
    return response


@login_required
@require_http_methods(["GET"])
def security_alerts_api(request):
    events = AuditEvent.objects.filter(actor_id=request.user.pk, resource_type="Authentication").filter(
        outcome__in=["failed", "blocked", "denied"]
    ).order_by("-created_at", "-id")[:50]
    return JsonResponse({"alerts": [{
        "id": event.pk, "action": event.action, "outcome": event.outcome,
        "created_at": event.created_at,
    } for event in events]})
