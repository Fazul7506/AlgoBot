from __future__ import annotations

HEALTH_STATUSES = ("healthy", "degraded", "down", "unknown")
ALERT_SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "EMERGENCY")
ALERT_CATEGORIES = (
    "Broker", "Trading", "Risk", "AI", "Strategy", "Infrastructure",
    "Security", "Database", "Performance", "Network",
)
ALERT_STATUSES = ("open", "acknowledged", "resolved", "suppressed")
INCIDENT_STATUSES = ("open", "investigating", "acknowledged", "resolved", "postmortem")
LOG_STREAMS = (
    "application", "trading", "broker", "ai", "risk", "strategy", "security",
    "authentication", "api", "database", "celery", "system", "infrastructure",
)
WEBSOCKET_EVENTS = (
    "HealthChanged", "AlertCreated", "AlertResolved", "IncidentCreated", "IncidentResolved",
    "BrokerDisconnected", "BrokerConnected", "StrategyCrashed", "AIFailed",
    "RiskLimitExceeded", "HighCPUUsage", "MemoryCritical", "DatabaseDown", "ServiceRecovered",
)
DEFAULT_THRESHOLDS = {"cpu": 85.0, "memory": 90.0, "disk": 90.0, "latency_ms": 2000.0, "drawdown": 10.0}
