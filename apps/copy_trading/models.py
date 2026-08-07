from django.conf import settings
from django.db import models
from . import constants as c
class SignalProvider(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='signal_provider_profiles'); display_name=models.CharField(max_length=120); bio=models.TextField(blank=True); verification_status=models.CharField(max_length=32,default='pending'); experience_level=models.CharField(max_length=32,blank=True); country=models.CharField(max_length=80,blank=True); followers=models.PositiveIntegerField(default=0); rating=models.FloatField(default=0); created_at=models.DateTimeField(auto_now_add=True)
class TradingStrategy(models.Model):
    provider=models.ForeignKey(SignalProvider,on_delete=models.CASCADE,related_name='strategies'); name=models.CharField(max_length=160); description=models.TextField(blank=True); category=models.CharField(max_length=40,choices=[(x,x.title()) for x in c.STRATEGY_CATEGORIES]); risk_level=models.CharField(max_length=32,default='medium'); subscription_price=models.DecimalField(max_digits=10,decimal_places=2,default=0); visibility=models.CharField(max_length=32,default='public'); performance_score=models.FloatField(default=0)
class StrategySubscription(models.Model):
    strategy=models.ForeignKey(TradingStrategy,on_delete=models.CASCADE,related_name='subscriptions'); follower=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='strategy_subscriptions'); status=models.CharField(max_length=32,default='active'); started_at=models.DateTimeField(auto_now_add=True); expires_at=models.DateTimeField(null=True,blank=True)
class TradeMirror(models.Model):
    provider_trade=models.CharField(max_length=120); follower_trade=models.CharField(max_length=120,blank=True); allocation=models.DecimalField(max_digits=10,decimal_places=4,default=1); multiplier=models.DecimalField(max_digits=10,decimal_places=4,default=1); status=models.CharField(max_length=32,default='pending')
class RevenueShare(models.Model):
    provider=models.ForeignKey(SignalProvider,on_delete=models.CASCADE); subscriber=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE); amount=models.DecimalField(max_digits=12,decimal_places=2); commission=models.DecimalField(max_digits=12,decimal_places=2,default=0); paid_at=models.DateTimeField(null=True,blank=True)
class PerformanceSnapshot(models.Model):
    strategy=models.ForeignKey(TradingStrategy,on_delete=models.CASCADE,related_name='performance_snapshots'); daily_return=models.FloatField(default=0); monthly_return=models.FloatField(default=0); yearly_return=models.FloatField(default=0); drawdown=models.FloatField(default=0); sharpe=models.FloatField(default=0); profit_factor=models.FloatField(default=0); win_rate=models.FloatField(default=0)
class Leaderboard(models.Model):
    strategy=models.ForeignKey(TradingStrategy,on_delete=models.CASCADE); provider=models.ForeignKey(SignalProvider,on_delete=models.CASCADE); ranking=models.PositiveIntegerField(); score=models.FloatField(default=0); period=models.CharField(max_length=32,default='monthly')
