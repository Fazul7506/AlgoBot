from django.conf import settings
from django.db import models
from . import constants as c

class RiskProfile(models.Model):
    LEVEL_CHOICES=[(v,v.replace('_',' ').title()) for v in c.RISK_LEVELS]
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='risk_profiles')
    profile_name=models.CharField(max_length=120,default='Default Risk Profile')
    risk_level=models.CharField(max_length=32,choices=LEVEL_CHOICES,default='moderate')
    max_risk_per_trade=models.DecimalField(max_digits=10,decimal_places=6,default=0.02)
    max_daily_loss=models.DecimalField(max_digits=10,decimal_places=6,default=0.04)
    max_daily_profit=models.DecimalField(max_digits=10,decimal_places=6,default=0.06)
    max_drawdown=models.DecimalField(max_digits=10,decimal_places=6,default=0.10)
    max_open_positions=models.PositiveIntegerField(default=10)
    max_exposure=models.DecimalField(max_digits=10,decimal_places=6,default=0.35)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: indexes=[models.Index(fields=['user','risk_level'])]
    def __str__(self): return f'{self.user} - {self.profile_name}'

class RiskRule(models.Model):
    RULE_CHOICES=[(v,v.replace('_',' ').title()) for v in c.RULE_TYPES]
    profile=models.ForeignKey(RiskProfile,on_delete=models.CASCADE,related_name='rules')
    rule_name=models.CharField(max_length=160)
    rule_type=models.CharField(max_length=64,choices=RULE_CHOICES)
    value=models.DecimalField(max_digits=18,decimal_places=8)
    enabled=models.BooleanField(default=True)
    priority=models.PositiveSmallIntegerField(default=100)
    class Meta: ordering=['priority','rule_name']

class RiskAssessment(models.Model):
    trade=models.ForeignKey('execution.Order',on_delete=models.CASCADE,related_name='risk_assessments')
    risk_score=models.PositiveSmallIntegerField(default=0)
    approved=models.BooleanField(default=False)
    rejection_reason=models.TextField(blank=True)
    assessment_time=models.DateTimeField(auto_now_add=True)
    adjusted_parameters=models.JSONField(default=dict,blank=True)

class Exposure(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='risk_exposures')
    symbol=models.CharField(max_length=40)
    market=models.CharField(max_length=80,blank=True)
    exposure_value=models.DecimalField(max_digits=20,decimal_places=8,default=0)
    percentage=models.DecimalField(max_digits=10,decimal_places=6,default=0)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: unique_together=('user','symbol','market')

class DrawdownHistory(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='drawdown_history')
    balance=models.DecimalField(max_digits=20,decimal_places=8)
    equity=models.DecimalField(max_digits=20,decimal_places=8)
    drawdown=models.DecimalField(max_digits=20,decimal_places=8,default=0)
    drawdown_percent=models.DecimalField(max_digits=10,decimal_places=6,default=0)
    timestamp=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-timestamp']

class KillSwitchEvent(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='kill_switch_events')
    reason=models.TextField()
    activated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='activated_kill_switches')
    activated_at=models.DateTimeField(auto_now_add=True)
    resolved_at=models.DateTimeField(null=True,blank=True)
    class Meta: indexes=[models.Index(fields=['user','resolved_at'])]
