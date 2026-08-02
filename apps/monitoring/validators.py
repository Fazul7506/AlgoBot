from .constants import ALERT_CATEGORIES, ALERT_SEVERITIES

def validate_severity(value):
    if value not in ALERT_SEVERITIES:
        raise ValueError(f"Unsupported alert severity: {value}")
    return value

def validate_category(value):
    if value not in ALERT_CATEGORIES:
        raise ValueError(f"Unsupported alert category: {value}")
    return value
