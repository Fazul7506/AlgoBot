from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from datetime import timedelta

from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.shortcuts import get_object_or_404
from rest_framework.response import Response

from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan
from apps.brokers.models import BrokerAccount, BrokerConnection, Position
from .serializers import AlertSerializer, AuditLogSerializer, BrokerHealthSerializer, IncidentSerializer, LogEntrySerializer, MetricSerializer, SystemHealthSerializer, TraceSpanSerializer
from .services import MonitoringEngine


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    data = MonitoringEngine().dashboard()
    if not request.user.is_staff:
        data["overall_system_health"] = "available"
    account_ids = BrokerAccount.objects.filter(user=request.user, status="active").values_list("id", flat=True)
    data["broker_status"] = (
        "connected"
        if BrokerConnection.objects.filter(broker_account_id__in=account_ids, status="connected").exists()
        else "not_connected"
    )
    data["current_trades"] = Position.objects.filter(account_id__in=account_ids, status="open").count()
    data["active_alerts"] = Alert.objects.filter(user=request.user).exclude(status="resolved").count()
    data["open_incidents"] = Incident.objects.filter(
        Q(assigned_to=request.user) | Q(alert__user=request.user)
    ).exclude(status="resolved").distinct().count()
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def health(request):
    return Response(SystemHealthSerializer(SystemHealth.objects.all()[:100], many=True).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def broker(request):
    return Response(BrokerHealthSerializer(BrokerHealth.objects.all()[:100], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def trading(request):
    return Response(MonitoringEngine().trading.snapshot())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def strategies(request):
    return Response(MonitoringEngine().strategy.snapshot())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ai(request):
    return Response(MonitoringEngine().ai.snapshot())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def risk(request):
    return Response(MonitoringEngine().risk.snapshot())


@api_view(["GET"])
@permission_classes([IsAdminUser])
def infrastructure(request):
    return Response(MonitoringEngine().infrastructure.snapshot())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def alerts(request):
    queryset = Alert.objects.all() if request.user.is_staff else Alert.objects.filter(user=request.user)
    return Response(AlertSerializer(queryset.order_by("-created_at")[:100], many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def acknowledge_alert(request):
    alert_id = request.data.get("id")
    if not alert_id:
        return Response({"detail": "Alert id is required."}, status=400)
    queryset = Alert.objects.all() if request.user.is_staff else Alert.objects.filter(user=request.user)
    alert = get_object_or_404(queryset, pk=alert_id)
    alert.acknowledge()
    return Response(AlertSerializer(alert).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def incidents(request):
    queryset = Incident.objects.all() if request.user.is_staff else Incident.objects.filter(
        Q(assigned_to=request.user) | Q(alert__user=request.user)
    ).distinct()
    return Response(IncidentSerializer(queryset.order_by("-started_at")[:100], many=True).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def metrics(request):
    return Response(MetricSerializer(Metric.objects.all()[:500], many=True).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def audit(request):
    return Response(AuditLogSerializer(AuditLog.objects.all()[:500], many=True).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def logs(request):
    return Response(LogEntrySerializer(LogEntry.objects.all()[:500], many=True).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def mission_events(request):
    """Safe, compact event stream for the staff Mission Control page."""
    try:
        limit = min(max(int(request.query_params.get("limit", 100)), 1), 250)
    except (TypeError, ValueError):
        limit = 100
    events = LogEntry.objects.all()
    level = str(request.query_params.get("level") or "").strip().upper()
    stream = str(request.query_params.get("stream") or "").strip().lower()
    status = str(request.query_params.get("status") or "").strip().lower()
    category = str(request.query_params.get("category") or "").strip().lower()
    source = str(request.query_params.get("source") or "").strip()[:120]
    operation_id = str(request.query_params.get("operation_id") or "").strip()[:100]
    search = str(request.query_params.get("search") or "").strip()[:160]
    try:
        offset = min(max(int(request.query_params.get("offset", 0)), 0), 100000)
    except (TypeError, ValueError):
        offset = 0
    try:
        since_minutes = int(request.query_params.get("since_minutes", 60))
        since_minutes = min(max(since_minutes, 1), 43200)
    except (TypeError, ValueError):
        since_minutes = 60
    since_value = str(request.query_params.get("since_minutes") or "").strip().lower()
    if since_value not in {"all", "0"}:
        events = events.filter(timestamp__gte=timezone.now() - timedelta(minutes=since_minutes))
    elif not request.query_params.get("start") and not request.query_params.get("end"):
        # Never scan an unbounded event table for the live console. Explicit custom
        # ranges are filtered below; "all" without a range means the supported 7-day window.
        events = events.filter(timestamp__gte=timezone.now() - timedelta(days=7))
    # Optional explicit time window for Mission Control's custom range selector.
    start_value = str(request.query_params.get("start") or "").strip()
    end_value = str(request.query_params.get("end") or "").strip()
    if start_value or end_value:
        start_dt = parse_datetime(start_value) if start_value else None
        end_dt = parse_datetime(end_value) if end_value else None
        if (start_value and start_dt is None) or (end_value and end_dt is None):
            return Response({"detail": "Invalid start or end datetime."}, status=400)
        if start_dt and timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
        if end_dt and timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
        if start_dt and end_dt and start_dt >= end_dt:
            return Response({"detail": "Start datetime must be before end datetime."}, status=400)
        if start_dt:
            events = events.filter(timestamp__gte=start_dt)
        if end_dt:
            events = events.filter(timestamp__lte=end_dt)
    if level:
        events = events.filter(level__iexact=level)
    if stream:
        events = events.filter(stream__iexact=stream)
    if source:
        events = events.filter(source__icontains=source)
    if operation_id:
        events = events.filter(context__operation_id__icontains=operation_id)
    if category:
        events = events.filter(context__category__iexact=category)
    if status:
        events = events.filter(context__status__iexact=status)
    if search:
        events = events.filter(
            Q(message__icontains=search) | Q(source__icontains=search) |
            Q(stream__icontains=search) | Q(context__category__icontains=search) |
            Q(context__status__icontains=search) | Q(context__operation_id__icontains=search)
        )
    # Fetch one extra row to signal whether another page exists without a costly count().
    try:
        page = list(events.order_by("-timestamp", "-id").values(
            "id", "stream", "level", "message", "source", "timestamp", "context"
        )[offset:offset + limit + 1])
    except DatabaseError:
        # Keep the console API response bounded and actionable during transient pool/database failures.
        return Response(
            {"detail": "Log storage is temporarily unavailable. Retry shortly.", "code": "MISSION_LOG_STORAGE_UNAVAILABLE"},
            status=503,
        )
    has_more = len(page) > limit
    page = page[:limit]
    for event in page:
        context = event.pop("context", {}) or {}
        # This endpoint is staff-only; expose structured diagnostic context, but never
        # serialize arbitrary request headers, credentials, or raw request bodies.
        event["category"] = str(context.get("category") or event["stream"])
        event["status"] = str(context.get("status") or ("failed" if event["level"] in {"ERROR", "CRITICAL"} else "recorded"))
        event["operation_id"] = context.get("operation_id")
        event["duration_ms"] = context.get("duration_ms")
        event["error_category"] = context.get("error_category")
        event["resolution"] = context.get("resolution")
        event["details"] = context.get("diagnostic_summary") or context.get("details")
    return Response({
        "results": page,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
        "limit": limit,
    })


@api_view(["GET"])
@permission_classes([IsAdminUser])
def traces(request):
    return Response(TraceSpanSerializer(TraceSpan.objects.all()[:500], many=True).data)
