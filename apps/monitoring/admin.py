from django.contrib import admin

from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan


class ReadOnlyMonitoringAdmin(admin.ModelAdmin):
    """Monitoring records are written by the runtime, not edited through admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemHealth)
class SystemHealthAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("service_name", "status", "response_time", "uptime", "timestamp")
    list_filter = ("status", "service_name")
    search_fields = ("service_name",)
    readonly_fields = [field.name for field in SystemHealth._meta.fields]
    date_hierarchy = "timestamp"


@admin.register(BrokerHealth)
class BrokerHealthAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("broker", "connection_status", "websocket_status", "api_status", "latency", "last_ping", "timestamp")
    list_filter = ("connection_status", "websocket_status", "api_status", "broker")
    search_fields = ("broker",)
    readonly_fields = [field.name for field in BrokerHealth._meta.fields]
    date_hierarchy = "timestamp"


@admin.register(Alert)
class AlertAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("title", "category", "severity", "status", "acknowledged", "resolved", "created_at")
    list_filter = ("category", "severity", "status", "acknowledged", "resolved")
    search_fields = ("title", "message", "source")
    readonly_fields = [field.name for field in Alert._meta.fields]
    date_hierarchy = "created_at"


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("user", "action", "module", "resource", "timestamp", "hash")
    list_filter = ("module", "action")
    search_fields = ("resource", "action", "module", "hash")
    readonly_fields = [field.name for field in AuditLog._meta.fields]
    date_hierarchy = "timestamp"


@admin.register(Metric)
class MetricAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("metric_name", "module", "value", "unit", "timestamp")
    list_filter = ("module", "metric_name")
    search_fields = ("metric_name", "module")
    readonly_fields = [field.name for field in Metric._meta.fields]
    date_hierarchy = "timestamp"


@admin.register(Incident)
class IncidentAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("title", "severity", "status", "assigned_to", "started_at", "resolved_at")
    list_filter = ("severity", "status")
    search_fields = ("title", "root_cause", "postmortem")
    readonly_fields = [field.name for field in Incident._meta.fields]
    date_hierarchy = "started_at"


@admin.register(LogEntry)
class LogEntryAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("stream", "level", "source", "message", "timestamp")
    list_filter = ("stream", "level", "source")
    search_fields = ("message", "source")
    readonly_fields = [field.name for field in LogEntry._meta.fields]
    date_hierarchy = "timestamp"


@admin.register(TraceSpan)
class TraceSpanAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("trace_id", "span_id", "operation", "module", "duration_ms", "status", "started_at")
    list_filter = ("module", "status", "operation")
    search_fields = ("trace_id", "span_id", "operation", "module")
    readonly_fields = [field.name for field in TraceSpan._meta.fields]
    date_hierarchy = "started_at"
