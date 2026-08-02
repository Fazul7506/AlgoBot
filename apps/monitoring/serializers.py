from rest_framework import serializers
from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan

class SystemHealthSerializer(serializers.ModelSerializer):
    class Meta: model = SystemHealth; fields = "__all__"
class BrokerHealthSerializer(serializers.ModelSerializer):
    class Meta: model = BrokerHealth; fields = "__all__"
class AlertSerializer(serializers.ModelSerializer):
    class Meta: model = Alert; fields = "__all__"
class AuditLogSerializer(serializers.ModelSerializer):
    class Meta: model = AuditLog; fields = "__all__"
class MetricSerializer(serializers.ModelSerializer):
    class Meta: model = Metric; fields = "__all__"
class IncidentSerializer(serializers.ModelSerializer):
    class Meta: model = Incident; fields = "__all__"
class LogEntrySerializer(serializers.ModelSerializer):
    class Meta: model = LogEntry; fields = "__all__"
class TraceSpanSerializer(serializers.ModelSerializer):
    class Meta: model = TraceSpan; fields = "__all__"
