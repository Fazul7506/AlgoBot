from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.automation.models import ApprovalRequest, ScheduledTask, Workflow, WorkflowExecution
from apps.deployment.models import BackupRecord, ClusterStatus, DeploymentRecord
from apps.monitoring.models import Alert, AuditLog, BrokerHealth, Incident, SystemHealth
from apps.risk.models import RiskProfile
from apps.brokers.models import BrokerAccount


@login_required
def operations_center(request, module="mission-control"):
    accounts = BrokerAccount.objects.filter(user=request.user).select_related("broker")
    workflows = Workflow.objects.filter(user=request.user)
    executions = WorkflowExecution.objects.filter(workflow__user=request.user)
    approvals = ApprovalRequest.objects.filter(workflow__user=request.user)
    schedules = ScheduledTask.objects.filter(workflow__user=request.user)
    alerts = Alert.objects.order_by("-created_at")[:20]
    incidents = Incident.objects.order_by("-started_at")[:20]
    health = SystemHealth.objects.order_by("-timestamp")[:50]
    broker_health = BrokerHealth.objects.order_by("-timestamp")[:20]
    deployments = DeploymentRecord.objects.order_by("-created_at")[:20]
    backups = BackupRecord.objects.order_by("-created_at")[:20]
    clusters = ClusterStatus.objects.order_by("name")[:20]
    audit = AuditLog.objects.filter(user=request.user).order_by("-timestamp")[:40]
    risk_profile = RiskProfile.objects.filter(user=request.user).order_by("-created_at").first()

    security = {
        "debug": bool(getattr(settings, "DEBUG", False)),
        "secure_ssl": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
        "csrf_secure": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "session_secure": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        "hsts": int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0),
        "live_enabled": bool(getattr(settings, "ALLOW_LIVE_TRADING", False)),
        "connected_accounts": accounts.count(),
    }
    security_score = sum((
        not security["debug"], security["secure_ssl"], security["csrf_secure"],
        security["session_secure"], security["hsts"] >= 31536000,
    )) * 20

    return render(request, "core/operations_center.html", {
        "module": module, "accounts": accounts, "workflows": workflows[:20],
        "workflow_count": workflows.count(), "running_workflows": executions.filter(status="running").count(),
        "failed_executions": executions.filter(status="failed").count(), "pending_approvals": approvals.filter(status="pending").count(),
        "scheduled_tasks": schedules.filter(status__in=["pending", "running"]).count(), "alerts": alerts,
        "open_alerts": Alert.objects.filter(status__in=["open", "acknowledged"]).count(), "incidents": incidents,
        "open_incidents": Incident.objects.filter(status__in=["open", "investigating", "mitigating"]).count(),
        "health": health, "broker_health": broker_health, "deployments": deployments, "backups": backups,
        "clusters": clusters, "audit": audit, "risk_profile": risk_profile, "security": security,
        "security_score": security_score, "now": timezone.now(),
    })
