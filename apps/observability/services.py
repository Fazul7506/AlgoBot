import time
from django.utils import timezone
from apps.monitoring.models import AuditLog as StructuredAuditLog
from .models import HealthCheck, SystemMetric, OperationalEvent, AuditEvent

class HealthService:
    """Centralized health state. External checks should be implemented by adapters."""
    def record(self, service, status, component="", latency_ms=0, message="", metadata=None):
        return HealthCheck.objects.create(
            service=service, component=component, status=status,
            latency_ms=latency_ms, message=message, metadata=metadata or {}
        )

    def snapshot(self):
        latest = {}
        for h in HealthCheck.objects.all():
            key = f"{h.service}:{h.component}"
            if key not in latest:
                latest[key] = h
        return list(latest.values())

class MetricsService:
    def record(self, name, value, unit="", source=""):
        return SystemMetric.objects.create(name=name, value=value, unit=unit, source=source)

class EventService:
    def emit(self, category, severity, title, message="", service="", trace_id="", metadata=None):
        return OperationalEvent.objects.create(
            category=category, severity=severity, title=title,
            message=message, service=service, trace_id=trace_id,
            metadata=metadata or {}
        )

class AuditService:
    def record(self, actor_id, action, resource_type="", resource_id="", outcome="success", ip_address=None, metadata=None):
        return AuditEvent.objects.create(
            actor_id=actor_id, action=action, resource_type=resource_type,
            resource_id=resource_id, outcome=outcome, ip_address=ip_address,
            metadata=metadata or {}
        )

class MonitoringService:
    @staticmethod
    def _audit_feed(actor_id=None, include_global=False):
        """Normalize structured operational records and application audit events."""
        if actor_id is not None:
            request_logs = StructuredAuditLog.objects.filter(user_id=actor_id)
            app_events = AuditEvent.objects.filter(actor_id=actor_id)
        elif include_global:
            request_logs = StructuredAuditLog.objects.all()
            app_events = AuditEvent.objects.all()
        else:
            return []
        items = []
        for record in request_logs.order_by("-timestamp", "-id")[:100]:
            items.append({
                "_sort": record.timestamp,
                "id": f"request-{record.pk}",
                "action": record.action,
                "resource_type": record.module,
                "resource_id": record.resource,
                "outcome": "recorded",
                "created_at": record.timestamp.isoformat(),
                "source": "request",
            })
        for event in app_events.order_by("-created_at", "-id")[:100]:
            items.append({
                "_sort": event.created_at,
                "id": f"event-{event.pk}",
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "outcome": event.outcome,
                "created_at": event.created_at.isoformat(),
                "source": "application",
            })
        items.sort(key=lambda item: item["_sort"], reverse=True)
        return [{key: value for key, value in item.items() if key != "_sort"} for item in items[:100]]

    def dashboard(self, actor_id=None, include_global=False):
        health = HealthService().snapshot()
        return {
            "health": [{
                "service": h.service, "component": h.component, "status": h.status,
                "latency_ms": h.latency_ms, "message": h.message,
                "checked_at": h.checked_at.isoformat()
            } for h in health],
            "metrics": [{
                "name": m.name, "value": m.value, "unit": m.unit,
                "source": m.source, "recorded_at": m.recorded_at.isoformat()
            } for m in SystemMetric.objects.all()[:100]],
            "events": [{
                "id": e.id, "category": e.category, "severity": e.severity,
                "title": e.title, "message": e.message, "service": e.service,
                "trace_id": e.trace_id, "created_at": e.created_at.isoformat()
            } for e in OperationalEvent.objects.all()[:100]],
            "audit": self._audit_feed(actor_id=actor_id, include_global=include_global),
        }
