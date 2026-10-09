import os

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .services import ClusterService


@login_required
def dashboard(request):
    return render(request, "deployment/deployment_dashboard.html", ClusterService().health())


def health(request):
    # This endpoint confirms the Django route is responsive, not that an
    # external cluster or deployment provider is healthy.
    return JsonResponse({"status": "ok", "component": "deployment-api", "infrastructure": "not_configured"})


@login_required
def status(request):
    details = ClusterService().health()
    return JsonResponse(details, status=503)


@login_required
def version(request):
    version_value = getattr(settings, "APP_VERSION", None) or os.environ.get("RENDER_GIT_COMMIT") or "unknown"
    return JsonResponse({"version": version_value, "source": "configured_runtime" if version_value != "unknown" else "unavailable"})


@login_required
@require_http_methods(["POST"])
def deployment(request):
    return JsonResponse({
        "status": "not_configured",
        "detail": "Deployment provider is not configured; no deployment was started.",
    }, status=501)


@login_required
@require_http_methods(["POST"])
def backups(request):
    return JsonResponse({
        "status": "not_configured",
        "detail": "Backup provider is not configured; no backup was scheduled.",
    }, status=501)


@login_required
@require_http_methods(["POST"])
def rollback(request):
    return JsonResponse({
        "status": "not_configured",
        "detail": "Deployment provider is not configured; no rollback was started.",
    }, status=501)


@login_required
@require_http_methods(["POST"])
def restore(request):
    return JsonResponse({
        "status": "not_configured",
        "detail": "Restore provider is not configured; no restore was started.",
    }, status=501)
