"""Independent trader-facing workspaces for operational features."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.automation.models import ScheduledTask, Workflow, WorkflowExecution
from apps.deployment.models import BackupRecord, ClusterStatus, DeploymentRecord
from apps.developer.models import APIKey
from apps.monitoring.models import AuditLog
from core.account_context import get_active_account
from core.models import Subscription


def _account(request):
    return get_active_account(request.user, request=request)


@login_required
def automation_workspace(request):
    workflows = Workflow.objects.filter(user=request.user).order_by("-updated_at", "-id")
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    schedules = ScheduledTask.objects.filter(workflow__user=request.user, status__in=["pending", "running"])
    return render(request, "core/automation_workspace.html", {"workflows": workflows[:20], "running": executions.filter(status="running").count(), "failed": executions.filter(status="failed").count(), "scheduled": schedules.count()})


@login_required
def bot_runtime_workspace(request):
    return render(request, "core/bot_runtime.html", {"deployments": DeploymentRecord.objects.filter(user=request.user).order_by("-created_at")[:15], "backups": BackupRecord.objects.filter(user=request.user).order_by("-created_at")[:10], "clusters": ClusterStatus.objects.order_by("name")[:10], "account": _account(request), "live_enabled": bool(getattr(settings, "ALLOW_LIVE_TRADING", False))})


@login_required
def audit_workspace(request):
    events = AuditLog.objects.filter(user=request.user).order_by("-timestamp")[:80]
    return render(request, "core/audit_log.html", {"events": events, "event_count": AuditLog.objects.filter(user=request.user).count()})


@login_required
def security_workspace(request):
    account = _account(request)
    keys = APIKey.objects.filter(user=request.user)
    subscription = Subscription.objects.filter(user=request.user).first()
    checks = [("Broker connection", bool(account and account.token_status == "active" and not account.is_token_expired)), ("Secure HTTPS session", bool(getattr(settings, "SESSION_COOKIE_SECURE", False))), ("Account protection", bool(request.user.is_active and request.user.has_usable_password())), ("Developer access", bool(keys.filter(status="active").exists()))]
    return render(request, "core/security_center.html", {"account": account, "keys_count": keys.filter(status="active").count(), "subscription": subscription, "checks": checks})
