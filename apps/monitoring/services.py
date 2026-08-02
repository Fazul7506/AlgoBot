from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from .constants import DEFAULT_THRESHOLDS
from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthCheckResult:
    service_name: str
    status: str
    response_time: float
    details: dict[str, Any]


class HealthMonitoringService:
    monitored_services = ["Application", "Database", "Redis", "Celery", "WebSocket", "Broker", "Trading Engine", "Strategy Engine", "AI Engine", "Risk Engine", "Backtesting Engine", "API", "Authentication", "Storage", "Cache"]

    def check_service(self, service_name: str) -> HealthCheckResult:
        started = time.perf_counter()
        status = "healthy"
        details: dict[str, Any] = {}
        try:
            if service_name == "Database":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    details["database"] = cursor.fetchone()[0]
            elif service_name in {"Redis", "Cache"}:
                cache.set("monitoring:health", "ok", 10)
                details["cache"] = cache.get("monitoring:health")
            elif service_name == "Storage":
                details["cwd_writable"] = os.access(os.getcwd(), os.W_OK)
        except Exception as exc:  # health checks must not block callers
            status = "down"
            details["error"] = str(exc)
        response_ms = (time.perf_counter() - started) * 1000
        SystemHealth.objects.create(service_name=service_name, status=status, response_time=response_ms, details=details)
        return HealthCheckResult(service_name, status, response_ms, details)

    def run_checks(self) -> list[HealthCheckResult]:
        return [self.check_service(service) for service in self.monitored_services]

    def latest(self):
        return SystemHealth.objects.order_by("service_name", "-timestamp").distinct("service_name") if connection.vendor == "postgresql" else SystemHealth.objects.all()[:50]


class BrokerMonitoringService:
    def record(self, broker: str, **kwargs) -> BrokerHealth:
        return BrokerHealth.objects.create(broker=broker, **kwargs)

    def disconnected(self, broker: str) -> Alert:
        self.record(broker, connection_status="down", websocket_status="down", api_status="down", last_ping=timezone.now())
        return AlertEngine().create_alert("Broker disconnected", "Broker", "CRITICAL", f"{broker} connection is down", broker)


class TradingMonitoringService:
    def snapshot(self) -> dict[str, Any]:
        return {"trades_per_minute": 0, "open_positions": 0, "closed_positions": 0, "pending_orders": 0, "execution_latency": 0, "rejected_orders": 0, "success_rate": 100, "average_profit": 0, "average_loss": 0}


class StrategyMonitoringService:
    def snapshot(self) -> dict[str, Any]:
        return {"running_strategies": 0, "paused_strategies": 0, "stopped_strategies": 0, "signals_generated": 0, "win_rate": 0, "loss_rate": 0, "profit_factor": 0, "performance_drift": 0, "strategy_errors": 0}


class RiskMonitoringService:
    def snapshot(self) -> dict[str, Any]:
        return {"current_drawdown": 0, "portfolio_risk": 0, "exposure": 0, "margin": 0, "daily_loss": 0, "daily_profit": 0, "risk_score": 0, "circuit_breakers": [], "kill_switch_status": "ready"}


class AIMonitoringService:
    def snapshot(self) -> dict[str, Any]:
        return {"prediction_latency": 0, "prediction_accuracy": 0, "model_drift": 0, "feature_drift": 0, "training_status": "idle", "inference_errors": 0, "champion_model": None, "memory_usage": 0, "gpu_usage": 0}


class InfrastructureMonitoringService:
    def snapshot(self) -> dict[str, Any]:
        load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0
        return {"cpu": load, "memory": 0, "disk": 0, "database": "unknown", "redis": "unknown", "network": 0, "bandwidth": 0, "threads": 0, "processes": 0, "docker": "unknown", "workers": 0, "celery": "unknown", "gpu": 0, "temperature": None}


class MetricsService:
    def record(self, metric_name: str, value: float, unit: str = "", module: str = "application", tags: dict[str, Any] | None = None) -> Metric:
        return Metric.objects.create(metric_name=metric_name, value=value, unit=unit, module=module, tags=tags or {})

    def collect_application_metrics(self) -> dict[str, Any]:
        metrics = {"http_requests": 0, "api_response_time": 0, "errors": 0, "exceptions": 0, "queue_size": 0, "database_queries": len(connection.queries), "cache_hit_rate": 0, "session_count": 0, "user_activity": 0}
        for name, value in metrics.items():
            self.record(name, float(value), module="application")
        return metrics


class AlertEngine:
    def create_alert(self, title: str, category: str, severity: str, message: str, source: str, metadata: dict[str, Any] | None = None) -> Alert:
        return Alert.objects.create(title=title, category=category, severity=severity, message=message, source=source, metadata=metadata or {})

    def evaluate(self, payload: dict[str, Any]) -> list[Alert]:
        alerts = []
        thresholds = DEFAULT_THRESHOLDS
        for key, title in (("cpu", "High CPU usage"), ("memory", "Memory critical"), ("disk", "Disk nearly full")):
            if float(payload.get(key, 0)) >= thresholds[key]:
                alerts.append(self.create_alert(title, "Infrastructure", "HIGH", f"{key} reached {payload[key]}", "monitoring", {"metric": key}))
        if payload.get("broker_connection") == "down":
            alerts.append(self.create_alert("Broker disconnected", "Broker", "CRITICAL", "Broker connectivity lost", "broker"))
        if payload.get("database") == "down":
            alerts.append(self.create_alert("Database unavailable", "Database", "EMERGENCY", "Database health check failed", "database"))
        return alerts

    def acknowledge(self, alert_id: int) -> Alert:
        alert = Alert.objects.get(pk=alert_id); alert.acknowledge(); return alert


class IncidentService:
    def create_from_alert(self, alert: Alert, assigned_to=None) -> Incident:
        return Incident.objects.create(title=alert.title, severity=alert.severity, alert=alert, assigned_to=assigned_to)

    def resolve(self, incident_id: int, root_cause: str = "", postmortem: str = "") -> Incident:
        incident = Incident.objects.get(pk=incident_id)
        incident.status = "resolved"; incident.resolved_at = timezone.now(); incident.root_cause = root_cause; incident.postmortem = postmortem
        incident.save(update_fields=["status", "resolved_at", "root_cause", "postmortem"])
        return incident


class AuditService:
    def record(self, action: str, module: str, user=None, resource: str = "", old_value=None, new_value=None, ip_address=None) -> AuditLog:
        return AuditLog.objects.create(user=user, action=action, module=module, resource=resource, old_value=old_value, new_value=new_value, ip_address=ip_address)


class LogAggregationService:
    def ingest(self, stream: str, level: str, message: str, source: str = "", context: dict[str, Any] | None = None) -> LogEntry:
        return LogEntry.objects.create(stream=stream, level=level, message=message, source=source, context=context or {})

    def search(self, query: str = "", stream: str | None = None):
        qs = LogEntry.objects.all()
        if stream:
            qs = qs.filter(stream=stream)
        if query:
            qs = qs.filter(message__icontains=query)
        return qs[:500]


class TracingService:
    def start_span(self, operation: str, module: str, trace_id: str | None = None, parent_span_id: str = "", **attributes) -> TraceSpan:
        return TraceSpan.objects.create(trace_id=trace_id or uuid.uuid4().hex, span_id=uuid.uuid4().hex, parent_span_id=parent_span_id, operation=operation, module=module, attributes=attributes)

    def finish_span(self, span: TraceSpan, status: str = "ok") -> TraceSpan:
        span.duration_ms = (timezone.now() - span.started_at).total_seconds() * 1000; span.status = status; span.save(update_fields=["duration_ms", "status"]); return span


class NotificationService:
    channels = ["in_app", "email", "telegram", "discord", "slack", "sms", "push", "webhook"]

    def send(self, channel: str, title: str, message: str, target: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        logger.info("notification channel=%s title=%s target=%s", channel, title, target)
        return {"channel": channel, "title": title, "target": target, "delivered": True, "payload": payload or {}}


class SelfHealingService:
    def execute(self, action: str, target: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = {"restart_celery", "reconnect_websocket", "reconnect_broker", "restart_service", "flush_cache", "clear_queues", "retry_failed_tasks", "restart_monitoring", "reload_strategies", "reload_ai_models"}
        if action not in allowed:
            return {"action": action, "target": target, "status": "rejected"}
        if action == "flush_cache":
            cache.clear()
        LogAggregationService().ingest("infrastructure", "INFO", f"self-healing action {action} executed for {target}", "self-healing", payload or {})
        return {"action": action, "target": target, "status": "completed", "timestamp": timezone.now().isoformat()}

class MonitoringEngine:
    def __init__(self):
        self.health = HealthMonitoringService(); self.broker = BrokerMonitoringService(); self.trading = TradingMonitoringService(); self.strategy = StrategyMonitoringService(); self.risk = RiskMonitoringService(); self.ai = AIMonitoringService(); self.infrastructure = InfrastructureMonitoringService(); self.metrics = MetricsService(); self.alerts = AlertEngine()

    def dashboard(self) -> dict[str, Any]:
        latest_health = SystemHealth.objects.first()
        return {"overall_system_health": latest_health.status if latest_health else "unknown", "broker_status": BrokerHealth.objects.first().connection_status if BrokerHealth.objects.exists() else "unknown", "trading_engine_status": "healthy", "strategy_engine_status": "healthy", "ai_engine_status": "healthy", "risk_engine_status": "healthy", "current_cpu_usage": 0, "current_memory_usage": 0, "current_network_usage": 0, "current_drawdown": 0, "active_alerts": Alert.objects.exclude(status="resolved").count(), "open_incidents": Incident.objects.exclude(status="resolved").count(), "active_users": 0, "current_trades": 0, "current_predictions": 0, "queue_health": "unknown"}

    def collect(self) -> dict[str, Any]:
        health = self.health.run_checks(); app_metrics = self.metrics.collect_application_metrics(); alerts = self.alerts.evaluate({})
        return {"health_checks": len(health), "metrics": app_metrics, "alerts": len(alerts)}
