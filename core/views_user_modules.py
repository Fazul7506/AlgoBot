"""Independent trader-facing workspaces for operational features."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.automation.models import ApprovalRequest, ScheduledTask, Workflow, WorkflowExecution
from apps.brokers.models import BrokerAccount
from apps.deployment.models import BackupRecord, ClusterStatus, DeploymentRecord
from apps.developer.models import APIKey
from apps.monitoring.models import Alert, AuditLog, Incident
from core.models import Subscription


def _account(request):
    return (
        BrokerAccount.objects.filter(user=request.user, status="active")
        .select_related("broker")
        .order_by("-is_preferred", "-last_synced_at", "-id")
        .first()
    )


@login_required
def mission_control(request):
    workflows = Workflow.objects.filter(user=request.user)
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    incidents = Incident.objects.filter(
        assigned_to=request.user,
        status__in=["open", "investigating", "mitigating"],
    )
    return render(
        request,
        "core/mission_control.html",
        {
            "account": _account(request),
            "workflow_count": workflows.count(),
            "running_bots": executions.filter(status="running").count(),
            "open_incidents": incidents.count(),
            "pending_approvals": ApprovalRequest.objects.filter(
                workflow__user=request.user, status="pending"
            ).count(),
            "recent_activity": executions.select_related("workflow").order_by("-started_at")[:8],
        },
    )


@login_required
def automation_workspace(request):
    workflows = Workflow.objects.filter(user=request.user).order_by("-updated_at", "-id")
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    schedules = ScheduledTask.objects.filter(
        workflow__user=request.user, status__in=["pending", "running"]
    )
    return render(
        request,
        "core/automation_workspace.html",
        {
            "workflows": workflows[:20],
            "running": executions.filter(status="running").count(),
            "failed": executions.filter(status="failed").count(),
            "scheduled": schedules.count(),
        },
    )


@login_required
def bot_runtime_workspace(request):
    # Deployments and backups are now owner-scoped. Cluster health is global
    # infrastructure telemetry and remains read-only for workspace users.
    return render(
        request,
        "core/bot_runtime.html",
        {
            "deployments": DeploymentRecord.objects.filter(user=request.user).order_by("-created_at")[:15],
            "backups": BackupRecord.objects.filter(user=request.user).order_by("-created_at")[:10],
            "clusters": ClusterStatus.objects.order_by("name")[:10],
            "account": _account(request),
            "live_enabled": bool(getattr(settings, "ALLOW_LIVE_TRADING", False)),
        },
    )


@login_required
def audit_workspace(request):
    events = AuditLog.objects.filter(user=request.user).order_by("-timestamp")[:80]
    return render(
        request,
        "core/audit_log.html",
        {"events": events, "event_count": AuditLog.objects.filter(user=request.user).count()},
    )


@login_required
def security_workspace(request):
    account = _account(request)
    keys = APIKey.objects.filter(user=request.user)
    subscription = Subscription.objects.filter(user=request.user).first()
    checks = [
        (
            "Broker connection",
            bool(account and account.token_status == "active" and not account.is_token_expired),
        ),
        ("Secure HTTPS session", bool(getattr(settings, "SESSION_COOKIE_SECURE", False))),
        ("Account protection", bool(request.user.is_active and request.user.has_usable_password())),
        ("Developer access", bool(keys.filter(status="active").exists())),
    ]
    return render(
        request,
        "core/security_center.html",
        {
            "account": account,
            "keys_count": keys.filter(status="active").count(),
            "subscription": subscription,
            "checks": checks,
        },
    )


@login_required
def alert_workspace(request):
    # user=NULL denotes a system-wide alert; user-owned alerts are isolated.
    alerts = Alert.objects.filter(Q(user=request.user) | Q(user__isnull=True)).order_by("-created_at")
    incidents = Incident.objects.filter(assigned_to=request.user).order_by("-started_at")[:20]
    open_count = alerts.filter(status__in=["open", "acknowledged"]).count()
    return render(
        request,
        "core/alert_center.html",
        {
            "alerts": alerts[:50],
            "incidents": incidents,
            "account": _account(request),
            "open_count": open_count,
        },
    )
