from __future__ import annotations

from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def liveness(request):
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness(request):
    checks = {"database": False, "cache": False}
    status = 200
    try:
        connections["default"].cursor().execute("SELECT 1")
        checks["database"] = True
    except OperationalError:
        status = 503
    try:
        cache.set("healthcheck", "ok", 5)
        checks["cache"] = cache.get("healthcheck") == "ok"
    except Exception:
        status = 503
    return Response({"status": "ready" if all(checks.values()) else "degraded", "checks": checks}, status=status)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return readiness(request)
