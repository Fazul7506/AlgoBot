from __future__ import annotations

from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from rest_framework.decorators import api_view, permission_classes
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


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def liveness(request): return Response({"status": "ok"})


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def readiness(request):
    checks, response_status = _check_readiness()
    return Response({"status": "ready" if all(checks.values()) else "degraded", "checks": checks}, status=response_status)


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def health(request):
    # Render's five-second probe must measure process liveness, not database/cache latency.
    # Dependency readiness remains available at /health/ready/.
    return Response({"status": "ok", "service": "algobot"})
