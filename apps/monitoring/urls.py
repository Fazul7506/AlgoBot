from django.urls import path
from . import api, views

urlpatterns = [
    path("monitoring/dashboard/", api.dashboard, name="monitoring-dashboard"),
    path("monitoring/health/", api.health, name="monitoring-health"),
    path("monitoring/broker/", api.broker, name="monitoring-broker"),
    path("monitoring/trading/", api.trading, name="monitoring-trading"),
    path("monitoring/strategies/", api.strategies, name="monitoring-strategies"),
    path("monitoring/ai/", api.ai, name="monitoring-ai"),
    path("monitoring/risk/", api.risk, name="monitoring-risk"),
    path("monitoring/infrastructure/", api.infrastructure, name="monitoring-infrastructure"),
    path("alerts/", api.alerts, name="alerts"),
    path("alerts/acknowledge/", api.acknowledge_alert, name="alerts-acknowledge"),
    path("incidents/", api.incidents, name="incidents"),
    path("metrics/", api.metrics, name="metrics"),
    path("audit/", api.audit, name="audit"),
    path("logs/", api.logs, name="logs"),
    path("traces/", api.traces, name="traces"),
    path("monitoring/ui/", views.dashboard, name="monitoring-ui"),
]
