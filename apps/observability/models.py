import hashlib
import json

from django.db import models
from django.utils import timezone

class HealthCheck(models.Model):
    STATUS = [("healthy","Healthy"),("degraded","Degraded"),("down","Down")]
    service = models.CharField(max_length=120)
    component = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="healthy")
    latency_ms = models.FloatField(default=0)
    message = models.TextField(blank=True)
    checked_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-checked_at"]

class SystemMetric(models.Model):
    name = models.CharField(max_length=120)
    value = models.FloatField(default=0)
    unit = models.CharField(max_length=40, blank=True)
    source = models.CharField(max_length=120, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at"]

class OperationalEvent(models.Model):
    SEVERITY = [("info","Info"),("warning","Warning"),("error","Error"),("critical","Critical")]
    category = models.CharField(max_length=80)
    severity = models.CharField(max_length=20, choices=SEVERITY, default="info")
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    service = models.CharField(max_length=120, blank=True)
    trace_id = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

class AuditEvent(models.Model):
    actor_id = models.IntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=120, blank=True)
    outcome = models.CharField(max_length=30, default="success")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    request_path = models.CharField(max_length=500, blank=True, db_index=True)
    http_method = models.CharField(max_length=10, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    module = models.CharField(max_length=120, blank=True, db_index=True)
    resource = models.CharField(max_length=220, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True, editable=False, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["actor_id", "-created_at"], name="obs_audit_actor_created_idx"),
                   models.Index(fields=["http_method", "-created_at"], name="obs_audit_method_created_idx")]

    def save(self, *args, **kwargs):
        if not self.hash and not self.request_path:
            if not self.previous_hash:
                previous = AuditEvent.objects.exclude(hash="").order_by("-created_at", "-id").first()
                self.previous_hash = previous.hash if previous and previous.hash else "genesis"
            payload = {
                "actor_id": self.actor_id, "action": self.action,
                "resource_type": self.resource_type, "resource_id": self.resource_id,
                "outcome": self.outcome, "ip_address": self.ip_address,
                "request_path": self.request_path, "http_method": self.http_method,
                "http_status": self.http_status, "module": self.module,
                "resource": self.resource, "old_value": self.old_value,
                "new_value": self.new_value, "metadata": self.metadata,
                "previous_hash": self.previous_hash,
                "created_at": self.created_at.isoformat() if self.created_at else None,
            }
            self.hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        super().save(*args, **kwargs)
