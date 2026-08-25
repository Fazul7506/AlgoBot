from __future__ import annotations

from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _check_readiness() -> tuple[dict[str, bool], int]:
    checks = {"database": False, "cache": False}; response_status = 200
    try:
        with connections["default"].cursor() as cursor: cursor.execute("SELECT 1")
        checks["database"] = True
    except OperationalError: response_status = 503
    try:
        cache.set("healthcheck", "ok", 5); checks["cache"] = cache.get("healthcheck") == "ok"
    except Exception: response_status = 503
    return checks, response_status


def _empty_head_response(request, *, status=200):
    """Return an empty response for HEAD probes as required by RFC 9110."""
    if request.method == "HEAD":
        return HttpResponse(status=status)
    return None


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
@throttle_classes([])
def liveness(request):
    if (response := _empty_head_response(request)) is not None:
        return response
    return Response({"status": "ok"})


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
@throttle_classes([])
def readiness(request):
    checks, response_status = _check_readiness()
    if (response := _empty_head_response(request, status=response_status)) is not None:
        return response
    return Response({"status": "ready" if all(checks.values()) else "degraded", "checks": checks}, status=response_status)


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    # Render's five-second probe must measure process liveness, not database/cache latency.
    # Dependency readiness remains available at /health/ready/.
    if (response := _empty_head_response(request)) is not None:
        return response
    return Response({"status": "ok", "service": "algobot"})
