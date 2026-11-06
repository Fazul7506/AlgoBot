from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Q
from django.shortcuts import render

from .models import Alert, Incident, LogEntry, Metric, SystemHealth
from apps.notifications.models import NotificationChannelConnection
from .services import MonitoringEngine


@login_required
def dashboard(request, template_name="monitoring/dashboard.html"):
    """Render monitoring telemetry from live database/broker state.

    The previous implementation only returned MonitoringEngine.dashboard(),
    which exposed keys that the template expected but never supplied (trading,
    strategy, AI and risk snapshots). It also used the first global health row,
    so a missing/stale telemetry record appeared as ``Unknown``.
    """
    engine = MonitoringEngine()

    # Always perform the inexpensive core checks when the operator refreshes
    # this page. Failures are recorded by the health service rather than being
    # allowed to break the monitoring UI.
    health_results = []
    if request.user.is_staff:
        for service in ("Application", "Database", "Cache", "Storage"):
            try:
                health_results.append(engine.health.check_service(service))
            except Exception:
                health_results.append(None)

    dashboard = engine.dashboard(user=request.user)
    dashboard["health_checks"] = len([result for result in health_results if result is not None])

    # Overall health includes every check shown here; a working database alone
    # must not mask a broken cache or unwritable storage.
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        if request.user.is_staff:
            checks_healthy = bool(health_results) and all(
                result is not None and result.status == "healthy" for result in health_results
            )
            dashboard["overall_system_health"] = "healthy" if checks_healthy else "degraded"
        else:
            dashboard["overall_system_health"] = "available"
    except Exception:
        dashboard["overall_system_health"] = "down"

    # Keep operational events and connected-channel details private to this account.
    visible_alerts = Alert.objects.filter(user=request.user)
    if request.user.is_staff:
        visible_alerts = Alert.objects.filter(Q(user=request.user) | Q(user__isnull=True))
    recent_events = visible_alerts.order_by("-created_at")[:6]
    channel_connections = NotificationChannelConnection.objects.filter(
        user=request.user, status="verified", provider__in=("gmail", "telegram")
    ).only("provider", "address", "external_id", "metadata", "status")
    connected_channels = {item.provider: item for item in channel_connections}

    # Only staff can inspect global infrastructure health. Other accounts see
    # the scoped health checks performed for this request and their own broker.
    if request.user.is_staff:
        service_rows = [
            {"name": result.service_name, "status": result.status, "response_time": result.response_time}
            for result in health_results if result is not None
        ]
        if not service_rows:
            service_rows = list(SystemHealth.objects.order_by("-timestamp").values(
                "service_name", "status", "response_time"
            )[:6])
            service_rows = [{"name": row["service_name"], "status": row["status"], "response_time": row["response_time"]} for row in service_rows]
    else:
        service_rows = [
            {"name": "Trading account", "status": dashboard["broker_status"], "response_time": None},
            {"name": "Application", "status": dashboard["overall_system_health"], "response_time": None},
        ]
        for provider, label in (("gmail", "Gmail notifications"), ("telegram", "Telegram notifications")):
            service_rows.append({"name": label, "status": "healthy" if provider in connected_channels else "not_connected", "response_time": None})

    recent_logs = list(LogEntry.objects.order_by("-timestamp").values("id", "stream", "level", "message", "source", "timestamp")[:250]) if request.user.is_staff else []
    metric_history = list(Metric.objects.filter(module="application").order_by("-timestamp").values(
        "metric_name", "value", "unit", "timestamp"
    )[:20])
    return render(request, template_name, {
        "dashboard": dashboard,
        "service_rows": service_rows,
        "recent_events": recent_events,
        "connected_channels": connected_channels,
        "metric_history": metric_history,
        "recent_logs": recent_logs,
    })


@staff_member_required(login_url="/login/")
def mission_control(request):
    """Render the separate, staff-only operational activity center."""
    return dashboard(request, template_name="monitoring/mission_control.html")
