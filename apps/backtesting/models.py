from django.conf import settings
from django.db import models
from django.utils import timezone

STATUS=[('pending','Pending'),('running','Running'),('completed','Completed'),('failed','Failed'),('cancelled','Cancelled')]
DIRECTION=[('long','Long'),('short','Short')]

class Backtest(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='backtests')
    strategy=models.CharField(max_length=160,db_index=True)
    symbol=models.CharField(max_length=40,db_index=True)
    timeframe=models.CharField(max_length=16,db_index=True)
    start_date=models.DateTimeField(); end_date=models.DateTimeField()
    status=models.CharField(max_length=24,choices=STATUS,default='pending',db_index=True)
    mode=models.CharField(max_length=32,default='candle_close')
    parameters=models.JSONField(default=dict,blank=True)
    result_snapshot=models.JSONField(default=dict,blank=True)
    result_version=models.PositiveIntegerField(default=1)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-created_at']; indexes=[models.Index(fields=['user','status']),models.Index(fields=['symbol','timeframe'])]

class BacktestTrade(models.Model):
    backtest=models.ForeignKey(Backtest,on_delete=models.CASCADE,related_name='trades')
    entry_time=models.DateTimeField(); exit_time=models.DateTimeField(null=True,blank=True)
    entry_price=models.DecimalField(max_digits=20,decimal_places=8); exit_price=models.DecimalField(max_digits=20,decimal_places=8,null=True,blank=True)
    direction=models.CharField(max_length=12,choices=DIRECTION); profit=models.DecimalField(max_digits=18,decimal_places=8,default=0); fees=models.DecimalField(max_digits=18,decimal_places=8,default=0)
    duration=models.DurationField(null=True,blank=True); metadata=models.JSONField(default=dict,blank=True)
    class Meta: ordering=['entry_time']; indexes=[models.Index(fields=['backtest','entry_time'])]

class BacktestStatistics(models.Model):
    backtest=models.OneToOneField(Backtest,on_delete=models.CASCADE,related_name='statistics')
    net_profit=models.DecimalField(max_digits=18,decimal_places=8,default=0); gross_profit=models.DecimalField(max_digits=18,decimal_places=8,default=0); gross_loss=models.DecimalField(max_digits=18,decimal_places=8,default=0)
    profit_factor=models.DecimalField(max_digits=12,decimal_places=4,default=0); expectancy=models.DecimalField(max_digits=12,decimal_places=4,default=0)
    win_rate=models.DecimalField(max_digits=8,decimal_places=4,default=0); loss_rate=models.DecimalField(max_digits=8,decimal_places=4,default=0)
    drawdown=models.DecimalField(max_digits=12,decimal_places=4,default=0); sharpe=models.DecimalField(max_digits=12,decimal_places=4,default=0); sortino=models.DecimalField(max_digits=12,decimal_places=4,default=0); calmar=models.DecimalField(max_digits=12,decimal_places=4,default=0)
    metrics=models.JSONField(default=dict,blank=True); equity_curve=models.JSONField(default=list,blank=True); monthly_returns=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class BacktestClusterJob(models.Model):
    backtest=models.ForeignKey(Backtest,on_delete=models.CASCADE,related_name='cluster_jobs')
    priority=models.PositiveSmallIntegerField(default=5); worker_id=models.CharField(max_length=120,blank=True); attempts=models.PositiveSmallIntegerField(default=0)
    status=models.CharField(max_length=24,choices=STATUS,default='pending'); scheduled_at=models.DateTimeField(default=timezone.now); locked_at=models.DateTimeField(null=True,blank=True)
