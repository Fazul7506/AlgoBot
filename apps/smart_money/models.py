from django.db import models
from django.utils import timezone

class MarketStructure(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=12,db_index=True)
    trend=models.CharField(max_length=40); bos_count=models.PositiveIntegerField(default=0); choch_count=models.PositiveIntegerField(default=0); mss_count=models.PositiveIntegerField(default=0)
    structure_strength=models.FloatField(default=0); confidence=models.FloatField(default=0); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
    class Meta: ordering=['-timestamp']; indexes=[models.Index(fields=['symbol','timeframe','-timestamp'])]
class OrderBlock(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=12,db_index=True); type=models.CharField(max_length=40)
    bullish=models.BooleanField(default=False); bearish=models.BooleanField(default=False); high=models.DecimalField(max_digits=20,decimal_places=8); low=models.DecimalField(max_digits=20,decimal_places=8)
    mitigated=models.BooleanField(default=False); broken=models.BooleanField(default=False); strength=models.FloatField(default=0); volume=models.DecimalField(max_digits=20,decimal_places=8,default=0); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']; indexes=[models.Index(fields=['symbol','timeframe','mitigated','broken'])]
class BreakerBlock(models.Model):
    order_block=models.ForeignKey(OrderBlock,on_delete=models.CASCADE,related_name='breakers'); direction=models.CharField(max_length=16); strength=models.FloatField(default=0); status=models.CharField(max_length=32,default='confirmed'); created_at=models.DateTimeField(auto_now_add=True)
class MitigationBlock(models.Model):
    order_block=models.ForeignKey(OrderBlock,on_delete=models.CASCADE,related_name='mitigations'); mitigated_at=models.DateTimeField(default=timezone.now); retested=models.BooleanField(default=False); status=models.CharField(max_length=32,default='first_touch')
class FairValueGap(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=12,db_index=True); bullish=models.BooleanField(default=False); bearish=models.BooleanField(default=False)
    high=models.DecimalField(max_digits=20,decimal_places=8); low=models.DecimalField(max_digits=20,decimal_places=8); filled=models.BooleanField(default=False); fill_percentage=models.FloatField(default=0); strength=models.FloatField(default=0)
class LiquidityZone(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=12,db_index=True); type=models.CharField(max_length=40); internal=models.BooleanField(default=False); external=models.BooleanField(default=False); equal_high=models.BooleanField(default=False); equal_low=models.BooleanField(default=False); strength=models.FloatField(default=0)
class LiquiditySweep(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=12,db_index=True); direction=models.CharField(max_length=20); swept_price=models.DecimalField(max_digits=20,decimal_places=8); reversal=models.BooleanField(default=False); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
class PremiumDiscountZone(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); high=models.DecimalField(max_digits=20,decimal_places=8); low=models.DecimalField(max_digits=20,decimal_places=8); equilibrium=models.DecimalField(max_digits=20,decimal_places=8); premium=models.DecimalField(max_digits=20,decimal_places=8); discount=models.DecimalField(max_digits=20,decimal_places=8)
class TradingSession(models.Model):
    session=models.CharField(max_length=40,db_index=True); status=models.CharField(max_length=20); open_time=models.DateTimeField(); close_time=models.DateTimeField(); volatility=models.FloatField(default=0)
class InstitutionalBias(models.Model):
    symbol=models.CharField(max_length=40,db_index=True); timeframe=models.CharField(max_length=12,db_index=True); bias=models.CharField(max_length=40); confidence=models.FloatField(default=0); reason=models.TextField(blank=True); timestamp=models.DateTimeField(default=timezone.now,db_index=True)
