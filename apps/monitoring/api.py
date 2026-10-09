from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from django.db.models import Q
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
def traces(request):
    return Response(TraceSpanSerializer(TraceSpan.objects.all()[:500], many=True).data)
