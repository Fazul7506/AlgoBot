from django.db import models
from django.utils import timezone
class OptimizationJob(models.Model):
    strategy=models.CharField(max_length=160,db_index=True); optimizer=models.CharField(max_length=80,db_index=True); status=models.CharField(max_length=24,default='pending',db_index=True)
    parameter_space=models.JSONField(default=dict,blank=True); resource_limits=models.JSONField(default=dict,blank=True); best_parameters=models.JSONField(default=dict,blank=True)
    started_at=models.DateTimeField(default=timezone.now); completed_at=models.DateTimeField(null=True,blank=True)
class OptimizationResult(models.Model):
    optimization_job=models.ForeignKey(OptimizationJob,on_delete=models.CASCADE,related_name='results')
    parameters=models.JSONField(default=dict); fitness=models.FloatField(default=0); win_rate=models.FloatField(default=0); profit_factor=models.FloatField(default=0); drawdown=models.FloatField(default=0); score=models.FloatField(default=0)
    iteration=models.PositiveIntegerField(default=0); created_at=models.DateTimeField(auto_now_add=True)
