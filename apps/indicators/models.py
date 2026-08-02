from django.db import models
from django.utils import timezone
from .constants import INDICATOR_CATEGORIES, TIMEFRAMES

class Indicator(models.Model):
    name = models.CharField(max_length=80, unique=True, db_index=True)
    category = models.CharField(max_length=40, choices=[(c,c) for c in INDICATOR_CATEGORIES], db_index=True)
    description = models.TextField(blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['category','name']
    def __str__(self): return self.name

class IndicatorValue(models.Model):
    symbol = models.CharField(max_length=40, db_index=True)
    timeframe = models.CharField(max_length=8, choices=[(t,t) for t in TIMEFRAMES], db_index=True)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='values')
    value = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['symbol','timeframe','indicator','-timestamp'])]

class TrendAnalysis(models.Model):
    symbol = models.CharField(max_length=40, db_index=True)
    timeframe = models.CharField(max_length=8, choices=[(t,t) for t in TIMEFRAMES], db_index=True)
    trend = models.CharField(max_length=30, db_index=True)
    strength = models.FloatField(default=0)
    confidence = models.FloatField(default=0)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

class SupportResistanceLevel(models.Model):
    LEVEL_TYPES = [('support','Support'),('resistance','Resistance'),('pivot','Pivot'),('dynamic','Dynamic')]
    symbol = models.CharField(max_length=40, db_index=True)
    timeframe = models.CharField(max_length=8, choices=[(t,t) for t in TIMEFRAMES], db_index=True)
    level = models.FloatField(db_index=True)
    type = models.CharField(max_length=20, choices=LEVEL_TYPES, db_index=True)
    touches = models.PositiveIntegerField(default=1)
    strength = models.FloatField(default=0)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

class PatternDetection(models.Model):
    symbol = models.CharField(max_length=40, db_index=True)
    timeframe = models.CharField(max_length=8, choices=[(t,t) for t in TIMEFRAMES], db_index=True)
    pattern = models.CharField(max_length=80, db_index=True)
    confidence = models.FloatField(default=0)
    direction = models.CharField(max_length=20, blank=True, db_index=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
