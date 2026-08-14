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
    actor_id = models.IntegerField(null=True, blank=True)
    action = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=120, blank=True)
    outcome = models.CharField(max_length=30, default="success")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
