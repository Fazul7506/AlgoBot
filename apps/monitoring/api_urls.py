from django.urls import path
from . import api

urlpatterns = [
    path("dashboard/", api.dashboard, name="monitoring-dashboard"),
    path("health/", api.health, name="monitoring-health"),
    path("broker/", api.broker, name="monitoring-broker"),
    path("trading/", api.trading, name="monitoring-trading"),
    path("strategies/", api.strategies, name="monitoring-strategies"),
    path("ai/", api.ai, name="monitoring-ai"),
    path("risk/", api.risk, name="monitoring-risk"),
    path("infrastructure/", api.infrastructure, name="monitoring-infrastructure"),
    path("alerts/", api.alerts, name="alerts"),
    path("alerts/acknowledge/", api.acknowledge_alert, name="alerts-acknowledge"),
    path("incidents/", api.incidents, name="incidents"),
    path("metrics/", api.metrics, name="metrics"),
    path("audit/", api.audit, name="audit"),
    path("logs/", api.logs, name="logs"),
    path("traces/", api.traces, name="traces"),
]
