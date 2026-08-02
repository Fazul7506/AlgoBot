class MonitoringError(Exception):
    """Base monitoring platform exception."""

class AlertRuleError(MonitoringError):
    """Raised when an alert rule cannot be evaluated."""

class SelfHealingError(MonitoringError):
    """Raised when a remediation action fails."""
