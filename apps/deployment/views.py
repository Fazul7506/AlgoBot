from django.http import JsonResponse
from django.shortcuts import render
from .services import ClusterService, DeploymentService, BackupService

def dashboard(request): return render(request, "deployment/deployment_dashboard.html", ClusterService().health())
def health(request): return JsonResponse({"status":"healthy"})
def status(request): return JsonResponse(ClusterService().health())
def version(request): return JsonResponse({"version":"enterprise"})
def deployment(request): return JsonResponse(DeploymentService().deploy("production","current").details)
def backups(request): return JsonResponse(BackupService().schedule().details)
def rollback(request): return JsonResponse(DeploymentService().rollback("production").details)
def restore(request): return JsonResponse({"status":"restore_validation_started"})
