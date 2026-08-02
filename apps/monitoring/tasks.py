try:
    from deriv_platform.celery import app
except Exception:
    app = None
from .services import AlertEngine, HealthMonitoringService, LogAggregationService, MetricsService, MonitoringEngine, SelfHealingService

def _task(fn):
    return app.task(fn) if app else fn

@_task
def run_health_checks(): return len(HealthMonitoringService().run_checks())
@_task
def collect_metrics(): return MetricsService().collect_application_metrics()
@_task
def aggregate_logs(): return LogAggregationService().ingest("system", "INFO", "log aggregation heartbeat", "monitoring").id
@_task
def evaluate_alerts(payload=None): return len(AlertEngine().evaluate(payload or {}))
@_task
def cleanup_incidents(): return 0
@_task
def run_self_healing(action="restart_monitoring", target="monitoring", payload=None): return SelfHealingService().execute(action, target, payload)
@_task
def archive_audit_logs(): return 0
@_task
def analyze_performance(): return MonitoringEngine().collect()
