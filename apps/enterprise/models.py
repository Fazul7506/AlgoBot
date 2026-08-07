from django.db import models

class EnterpriseState(models.Model):
    system_status = models.CharField(max_length=32, default="operational")
    market_regime = models.CharField(max_length=40, default="neutral")
    risk_level = models.CharField(max_length=32, default="normal")
    ai_mode = models.CharField(max_length=32, default="supervised")
    health_score = models.FloatField(default=100.0)
    updated_at = models.DateTimeField(auto_now=True)

class AIAgent(models.Model):
    name = models.CharField(max_length=120, unique=True)
    role = models.CharField(max_length=80)
    status = models.CharField(max_length=32, default="idle")
    confidence = models.FloatField(default=0.0)
    last_execution = models.DateTimeField(null=True, blank=True)

class OptimizationSession(models.Model):
    objective = models.CharField(max_length=160)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="running")
    results = models.JSONField(default=dict, blank=True)

class KnowledgeArticle(models.Model):
    category = models.CharField(max_length=80, db_index=True)
    title = models.CharField(max_length=160)
    content = models.TextField()
    source = models.CharField(max_length=160, blank=True)
    confidence = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

class GovernancePolicy(models.Model):
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=80)
    rule = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
