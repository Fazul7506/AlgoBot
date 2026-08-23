from __future__ import annotations

from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _check_readiness() -> tuple[dict[str, bool], int]:
    """Run readiness checks without wrapping the helper as a DRF view."""
    checks = {"database": False, "cache": False}
    status = 200

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = True
    except OperationalError:
        status = 503

    try:
        cache.set("healthcheck", "ok", 5)
        checks["cache"] = cache.get("healthcheck") == "ok"
    except Exception:
        status = 503

    return checks, status


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def liveness(request):
    """Confirm that the application process is alive."""
    return Response({"status": "ok"})


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def readiness(request):
    """Confirm that required dependencies are available."""
    checks, status = _check_readiness()
    return Response(
        {
            "status": "ready" if all(checks.values()) else "degraded",
            "checks": checks,
        },
        status=status,
    )


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def health(request):
    """Combined health endpoint for Render and external uptime monitors."""
    checks, status = _check_readiness()
    return Response(
        {
            "status": "ready" if all(checks.values()) else "degraded",
            "checks": checks,
        },
        status=status,
    )
