from django.db import models
from django.utils import timezone
from . import constants as c

class AIModel(models.Model):
    name=models.CharField(max_length=160,db_index=True)
    version=models.CharField(max_length=40,default="1.0.0")
    algorithm=models.CharField(max_length=64,choices=[(x,x.replace('_',' ').title()) for x in c.ALGORITHMS])
    framework=models.CharField(max_length=80,default="sklearn")
    status=models.CharField(max_length=32,choices=[(x,x.title()) for x in c.MODEL_STATUS],default="experimental",db_index=True)
    accuracy=models.FloatField(default=0); precision=models.FloatField(default=0); recall=models.FloatField(default=0); f1_score=models.FloatField(default=0); auc=models.FloatField(default=0)
    metadata=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=("name","version"); indexes=[models.Index(fields=["status","algorithm"])]
    def __str__(self): return f"{self.name} v{self.version}"

class ModelVersion(models.Model):
    model=models.ForeignKey(AIModel,on_delete=models.CASCADE,related_name="versions")
    version=models.CharField(max_length=40); training_dataset=models.CharField(max_length=255,blank=True)
    feature_set=models.JSONField(default=dict,blank=True); hyperparameters=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=("model","version"); ordering=["-created_at"]

class Prediction(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=16,db_index=True)
    prediction=models.CharField(max_length=64); probability=models.FloatField(default=0); confidence=models.FloatField(default=0)
    expected_return=models.FloatField(default=0); risk_score=models.FloatField(default=0); payload=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-created_at"]; indexes=[models.Index(fields=["symbol","timeframe","-created_at"])]

class PredictionOutcome(models.Model):
    prediction=models.OneToOneField(Prediction,on_delete=models.CASCADE,related_name="outcome")
    actual_direction=models.CharField(max_length=32,blank=True)
    actual_return=models.FloatField(default=0)
    correct=models.BooleanField(null=True,db_index=True)
    horizon_candles=models.PositiveIntegerField(default=1)
    resolved_at=models.DateTimeField(null=True,blank=True,db_index=True)
    details=models.JSONField(default=dict,blank=True)
    class Meta: ordering=["-resolved_at"]; indexes=[models.Index(fields=["correct","resolved_at"])]

class FeatureVector(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=16,db_index=True); features=models.JSONField(default=dict)
    feature_hash=models.CharField(max_length=64,unique=True); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
    class Meta: ordering=["-timestamp"]

class TrainingJob(models.Model):
    model=models.ForeignKey(AIModel,on_delete=models.CASCADE,related_name="training_jobs",null=True,blank=True)
    status=models.CharField(max_length=32,default="pending",db_index=True); started_at=models.DateTimeField(null=True,blank=True); completed_at=models.DateTimeField(null=True,blank=True); duration=models.FloatField(default=0); metrics=models.JSONField(default=dict,blank=True)
    class Meta: ordering=["-started_at"]

class AIRecommendation(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); recommendation=models.CharField(max_length=32,choices=[(x,x) for x in c.RECOMMENDATIONS])
    confidence=models.FloatField(default=0); reason=models.TextField(blank=True); evidence=models.JSONField(default=dict,blank=True); risk_level=models.CharField(max_length=32,default="medium"); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
    class Meta: ordering=["-timestamp"]

class MarketRegime(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); regime=models.CharField(max_length=32,choices=[(x,x.replace('_',' ').title()) for x in c.REGIMES]); confidence=models.FloatField(default=0); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
    class Meta: ordering=["-timestamp"]

class AnomalyEvent(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); anomaly_type=models.CharField(max_length=64); score=models.FloatField(default=0); details=models.JSONField(default=dict,blank=True); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
