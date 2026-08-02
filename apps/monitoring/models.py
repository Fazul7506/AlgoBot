from __future__ import annotations

import hashlib
import json
from django.conf import settings
from django.db import models
from django.utils import timezone

from .constants import ALERT_CATEGORIES, ALERT_SEVERITIES, ALERT_STATUSES, HEALTH_STATUSES, INCIDENT_STATUSES, LOG_STREAMS


def choices(values):
    return [(value, value) for value in values]


class SystemHealth(models.Model):
    service_name = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=20, choices=choices(HEALTH_STATUSES), default="unknown", db_index=True)
    cpu = models.FloatField(default=0)
    memory = models.FloatField(default=0)
    disk = models.FloatField(default=0)
    network = models.FloatField(default=0)
    response_time = models.FloatField(default=0, help_text="Response time in milliseconds")
    uptime = models.FloatField(default=0, help_text="Uptime in seconds")
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["service_name", "-timestamp"]), models.Index(fields=["status", "-timestamp"])]

    def __str__(self):
        return f"{self.service_name}: {self.status}"


class BrokerHealth(models.Model):
    broker = models.CharField(max_length=120, db_index=True)
    connection_status = models.CharField(max_length=40, default="unknown", db_index=True)
    latency = models.FloatField(default=0)
    websocket_status = models.CharField(max_length=40, default="unknown")
    api_status = models.CharField(max_length=40, default="unknown")
    packet_loss = models.FloatField(default=0)
    reconnect_attempts = models.PositiveIntegerField(default=0)
    authorization_status = models.CharField(max_length=40, default="unknown")
    heartbeat = models.DateTimeField(null=True, blank=True)
    trade_success_rate = models.FloatField(default=0)
    order_latency = models.FloatField(default=0)
    last_ping = models.DateTimeField(null=True, blank=True)
    last_trade = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["broker", "-timestamp"])]


class Alert(models.Model):
    title = models.CharField(max_length=220)
    category = models.CharField(max_length=40, choices=choices(ALERT_CATEGORIES), db_index=True)
    severity = models.CharField(max_length=20, choices=choices(ALERT_SEVERITIES), db_index=True)
    status = models.CharField(max_length=20, choices=choices(ALERT_STATUSES), default="open", db_index=True)
    message = models.TextField()
    source = models.CharField(max_length=160, db_index=True)
    acknowledged = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["severity", "status", "-created_at"])]

    def acknowledge(self):
        self.acknowledged = True; self.status = "acknowledged"; self.acknowledged_at = timezone.now(); self.save(update_fields=["acknowledged", "status", "acknowledged_at"])

    def resolve(self):
        self.resolved = True; self.status = "resolved"; self.resolved_at = timezone.now(); self.save(update_fields=["resolved", "status", "resolved_at"])


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=120, db_index=True)
    module = models.CharField(max_length=120, db_index=True)
    resource = models.CharField(max_length=220, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, editable=False, db_index=True)

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if not self.previous_hash:
            previous = AuditLog.objects.order_by("-timestamp").first()
            self.previous_hash = previous.hash if previous else "genesis"
        payload = json.dumps({"user": self.user_id, "action": self.action, "module": self.module, "resource": self.resource, "old": self.old_value, "new": self.new_value, "ip": self.ip_address, "previous": self.previous_hash}, sort_keys=True, default=str)
        self.hash = hashlib.sha256(payload.encode()).hexdigest()
        super().save(*args, **kwargs)


class Metric(models.Model):
    metric_name = models.CharField(max_length=160, db_index=True)
    value = models.FloatField()
    unit = models.CharField(max_length=40, blank=True)
    module = models.CharField(max_length=120, db_index=True)
    tags = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["metric_name", "module", "-timestamp"])]


class Incident(models.Model):
    title = models.CharField(max_length=220)
    severity = models.CharField(max_length=20, choices=choices(ALERT_SEVERITIES), db_index=True)
    status = models.CharField(max_length=30, choices=choices(INCIDENT_STATUSES), default="open", db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    alert = models.ForeignKey(Alert, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents")
    root_cause = models.TextField(blank=True)
    postmortem = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class LogEntry(models.Model):
    stream = models.CharField(max_length=40, choices=choices(LOG_STREAMS), db_index=True)
    level = models.CharField(max_length=20, default="INFO", db_index=True)
    message = models.TextField()
    source = models.CharField(max_length=160, blank=True, db_index=True)
    context = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["stream", "level", "-timestamp"])]


class TraceSpan(models.Model):
    trace_id = models.CharField(max_length=64, db_index=True)
    span_id = models.CharField(max_length=64, db_index=True)
    parent_span_id = models.CharField(max_length=64, blank=True)
    operation = models.CharField(max_length=160, db_index=True)
    module = models.CharField(max_length=120, db_index=True)
    duration_ms = models.FloatField(default=0)
    status = models.CharField(max_length=30, default="ok")
    attributes = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
