from django.conf import settings
from django.db import models
from django.utils import timezone
from . import constants as c

class Strategy(models.Model):
    name=models.CharField(max_length=160)
    slug=models.SlugField(max_length=180,unique=True)
    description=models.TextField(blank=True)
    category=models.CharField(max_length=80,choices=[(x,x) for x in c.STRATEGY_CATEGORIES])
    version=models.CharField(max_length=32,default='1.0.0')
    enabled=models.BooleanField(default=True,db_index=True)
    author=models.CharField(max_length=160,blank=True)
    lifecycle_state=models.CharField(max_length=32,choices=[(x,x.title()) for x in c.LIFECYCLE_STATES],default='created',db_index=True)
    module_path=models.CharField(max_length=255,blank=True)
    priority=models.PositiveSmallIntegerField(default=5)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['name']; indexes=[models.Index(fields=['enabled','category']),models.Index(fields=['slug','version'])]
    def __str__(self): return f'{self.name} v{self.version}'

class StrategyConfiguration(models.Model):
    strategy=models.ForeignKey(Strategy,on_delete=models.CASCADE,related_name='configurations')
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='strategy_configurations')
    broker_account=models.ForeignKey('broker.BrokerAccount',on_delete=models.SET_NULL,null=True,blank=True,related_name='strategy_configurations')
    parameters=models.JSONField(default=dict,blank=True)
    timeframe=models.CharField(max_length=16,default='M1',db_index=True)
    symbol=models.CharField(max_length=40,db_index=True)
    risk_profile=models.CharField(max_length=32,choices=[(x,x.title()) for x in c.RISK_PROFILES],default='balanced')
    schedule=models.CharField(max_length=32,choices=[(x,x.replace('_',' ').title()) for x in c.SCHEDULE_TYPES],default='every_candle')
    enabled=models.BooleanField(default=True,db_index=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: unique_together=[('strategy','user','symbol','timeframe')]; indexes=[models.Index(fields=['user','enabled']),models.Index(fields=['symbol','timeframe'])]

class StrategyExecution(models.Model):
    strategy=models.ForeignKey(Strategy,on_delete=models.CASCADE,related_name='executions')
    configuration=models.ForeignKey(StrategyConfiguration,on_delete=models.SET_NULL,null=True,blank=True,related_name='executions')
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=16,db_index=True)
    signal=models.CharField(max_length=32,choices=[(x,x) for x in c.SIGNAL_TYPES],default='HOLD')
    confidence=models.DecimalField(max_digits=5,decimal_places=2,default=0)
    status=models.CharField(max_length=24,choices=[(x,x.title()) for x in c.EXECUTION_STATUS],default='pending',db_index=True)
    latency_ms=models.FloatField(default=0); error=models.TextField(blank=True); context=models.JSONField(default=dict,blank=True)
    started_at=models.DateTimeField(default=timezone.now); completed_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['-started_at']; indexes=[models.Index(fields=['strategy','status']),models.Index(fields=['symbol','timeframe','-started_at'])]

class StrategyPerformance(models.Model):
    strategy=models.OneToOneField(Strategy,on_delete=models.CASCADE,related_name='performance')
    total_trades=models.PositiveIntegerField(default=0); wins=models.PositiveIntegerField(default=0); losses=models.PositiveIntegerField(default=0)
    win_rate=models.DecimalField(max_digits=6,decimal_places=2,default=0); profit_factor=models.DecimalField(max_digits=12,decimal_places=4,default=0)
    expectancy=models.DecimalField(max_digits=12,decimal_places=4,default=0); net_profit=models.DecimalField(max_digits=18,decimal_places=8,default=0)
    drawdown=models.DecimalField(max_digits=12,decimal_places=4,default=0); sharpe_ratio=models.DecimalField(max_digits=12,decimal_places=4,default=0)
    last_updated=models.DateTimeField(default=timezone.now)

class StrategySignal(models.Model):
    strategy=models.ForeignKey(Strategy,on_delete=models.CASCADE,related_name='signals')
    configuration=models.ForeignKey(StrategyConfiguration,on_delete=models.SET_NULL,null=True,blank=True,related_name='signals')
    symbol=models.CharField(max_length=40,db_index=True); signal=models.CharField(max_length=32,choices=[(x,x) for x in c.SIGNAL_TYPES])
    confidence=models.DecimalField(max_digits=5,decimal_places=2,default=0); entry_price=models.DecimalField(max_digits=20,decimal_places=8,null=True,blank=True)
    stop_loss=models.DecimalField(max_digits=20,decimal_places=8,null=True,blank=True); take_profit=models.DecimalField(max_digits=20,decimal_places=8,null=True,blank=True)
    metadata=models.JSONField(default=dict,blank=True); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
    class Meta: ordering=['-timestamp']; indexes=[models.Index(fields=['strategy','symbol','-timestamp'])]
