from django.db import models

class DeploymentRecord(models.Model):
    environment = models.CharField(max_length=40, db_index=True)
    version = models.CharField(max_length=80)
    strategy = models.CharField(max_length=40, default="rolling")
    status = models.CharField(max_length=32, default="pending", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class BackupRecord(models.Model):
    target = models.CharField(max_length=80)
    backup_type = models.CharField(max_length=40, default="incremental")
    status = models.CharField(max_length=32, default="scheduled")
    location = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class EnvironmentConfig(models.Model):
    name = models.CharField(max_length=40, unique=True)
    variables = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

class SecretRecord(models.Model):
    name = models.CharField(max_length=120, unique=True)
    provider = models.CharField(max_length=40, default="kubernetes")
    rotated_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="managed")

class ClusterStatus(models.Model):
    name = models.CharField(max_length=120, unique=True)
    region = models.CharField(max_length=80)
    health = models.CharField(max_length=32, default="healthy")
    metrics = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
