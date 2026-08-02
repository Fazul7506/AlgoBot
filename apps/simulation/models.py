from django.conf import settings
from django.db import models
class SimulationRun(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='simulation_runs')
    mode=models.CharField(max_length=32,db_index=True); status=models.CharField(max_length=24,default='pending'); config=models.JSONField(default=dict,blank=True); results=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
class ReplaySession(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='replay_sessions')
    backtest_id=models.PositiveIntegerField(null=True,blank=True); state=models.CharField(max_length=24,default='stopped'); speed=models.FloatField(default=1.0); cursor=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
