"""Independent trader-facing workspaces for operational features.

These views deliberately keep implementation/phase/model details out of the
normal trading UI. Each workspace owns a distinct user task instead of
rendering the same operations dashboard with a different title.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.automation.models import ApprovalRequest, ScheduledTask, Workflow, WorkflowExecution
from apps.brokers.models import BrokerAccount
from apps.deployment.models import BackupRecord, ClusterStatus, DeploymentRecord
from apps.monitoring.models import Alert, AuditLog, BrokerHealth, Incident
from core.models import Subscription
from apps.developer.models import APIKey


def _account(request):
    return (BrokerAccount.objects.filter(user=request.user, status="active")
            .select_related("broker").order_by("-is_preferred", "-last_synced_at", "-id").first())


@login_required
def mission_control(request):
    account = _account(request)
    workflows = Workflow.objects.filter(user=request.user)
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    open_incidents = Incident.objects.filter(assigned_to=request.user, status__in=["open", "investigating", "mitigating"])
    return render(request, "core/mission_control.html", {
        "account": account,
        "workflow_count": workflows.count(),
        "running_bots": executions.filter(status="running").count(),
        "open_incidents": open_incidents.count(),
        "pending_approvals": ApprovalRequest.objects.filter(workflow__user=request.user, status="pending").count(),
        "recent_activity": executions.order_by("-started_at")[:8],
    })


@login_required
def automation_workspace(request):
    workflows = Workflow.objects.filter(user=request.user).order_by("-updated_at", "-id")
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    schedules = ScheduledTask.objects.filter(workflow__user=request.user, status__in=["pending", "running"])
    return render(request, "core/automation_workspace.html", {
        "workflows": workflows[:20],
        "running": executions.filter(status="running").count(),
        "failed": executions.filter(status="failed").count(),
        "scheduled": schedules.count(),
    })


@login_required
def bot_runtime_workspace(request):
    deployments = DeploymentRecord.objects.order_by("-created_at")[:15]
    backups = BackupRecord.objects.order_by("-created_at")[:10]
    clusters = ClusterStatus.objects.order_by("name")[:10]
    account = _account(request)
    return render(request, "core/bot_runtime.html", {
        "deployments": deployments, "backups": backups, "clusters": clusters,
        "account": account, "live_enabled": bool(getattr(settings, "ALLOW_LIVE_TRADING", False)),
    })


@login_required
def audit_workspace(request):
    events = AuditLog.objects.filter(user=request.user).order_by("-timestamp")[:80]
    return render(request, "core/audit_log.html", {
        "events": events,
        "event_count": AuditLog.objects.filter(user=request.user).count(),
    })


@login_required
def security_workspace(request):
    account = _account(request)
    keys = APIKey.objects.filter(user=request.user)
    subscription = Subscription.objects.filter(user=request.user).first()
    checks = [
        ("Broker connection", bool(account and account.token_status == "active" and not account.is_token_expired)),
        ("Secure HTTPS session", bool(getattr(settings, "SESSION_COOKIE_SECURE", False))),
        ("Account protection", request.user.is_authenticated),
        ("Developer keys", keys.filter(status="active").exists()),
    ]
    return render(request, "core/security_center.html", {
        "account": account, "keys_count": keys.filter(status="active").count(),
        "subscription": subscription, "checks": checks,
    })


@login_required
def alert_workspace(request):
    # Alerts are system-wide records, but only show records plausibly belonging
    # to this user/account when metadata contains an owner; unowned platform
    # alerts remain visible because they can affect every trader.
    account = _account(request)
    alerts = Alert.objects.order_by("-created_at")[:50]
    incidents = Incident.objects.filter(assigned_to=request.user).order_by("-started_at")[:20]
    return render(request, "core/alert_center.html", {
        "alerts": alerts, "incidents": incidents, "account": account,
        "open_count": alerts.filter(status__in=["open", "acknowledged"]).count(),
    })
