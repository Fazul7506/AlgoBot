from django.contrib import admin
from .models import Alert, AuditLog, BrokerHealth, Incident, LogEntry, Metric, SystemHealth, TraceSpan
for model in (SystemHealth, BrokerHealth, Alert, AuditLog, Metric, Incident, LogEntry, TraceSpan):
    admin.site.register(model)
