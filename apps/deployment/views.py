from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .services import ClusterService, DeploymentService, BackupService

@login_required
def dashboard(request): return render(request, "deployment/deployment_dashboard.html", ClusterService().health())
def health(request): return JsonResponse({"status":"healthy"})
@login_required
def status(request): return JsonResponse(ClusterService().health())
@login_required
def version(request): return JsonResponse({"version":"enterprise"})
@login_required
@require_http_methods(["POST"])
def deployment(request): return JsonResponse(DeploymentService().deploy("production","current").details)
@login_required
@require_http_methods(["POST"])
def backups(request): return JsonResponse(BackupService().schedule().details)
@login_required
@require_http_methods(["POST"])
def rollback(request): return JsonResponse(DeploymentService().rollback("production").details)
@login_required
@require_http_methods(["POST"])
def restore(request): return JsonResponse({"status":"restore_validation_started"})
