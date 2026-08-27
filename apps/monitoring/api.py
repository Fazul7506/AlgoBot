from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan
from .serializers import AlertSerializer, AuditLogSerializer, BrokerHealthSerializer, IncidentSerializer, LogEntrySerializer, MetricSerializer, SystemHealthSerializer, TraceSpanSerializer
from .services import AlertEngine, MonitoringEngine


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    return Response(MonitoringEngine().dashboard())


@api_view(["GET"])
def health(request):
    return Response(SystemHealthSerializer(SystemHealth.objects.all()[:100], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def infrastructure(request):
    return Response(MonitoringEngine().infrastructure.snapshot())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def alerts(request):
    return Response(AlertSerializer(Alert.objects.all()[:100], many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def acknowledge_alert(request):
    alert = AlertEngine().acknowledge(request.data.get("id"))
    return Response(AlertSerializer(alert).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def incidents(request):
    return Response(IncidentSerializer(Incident.objects.all()[:100], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def metrics(request):
    return Response(MetricSerializer(Metric.objects.all()[:500], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit(request):
    return Response(AuditLogSerializer(AuditLog.objects.all()[:500], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def logs(request):
    return Response(LogEntrySerializer(LogEntry.objects.all()[:500], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traces(request):
    return Response(TraceSpanSerializer(TraceSpan.objects.all()[:500], many=True).data)
