from decimal import Decimal
from django.db import models
class Position(models.Model):
    order=models.OneToOneField('execution.Order',on_delete=models.CASCADE,related_name='position')
    symbol=models.CharField(max_length=40); entry_price=models.DecimalField(max_digits=18,decimal_places=8); current_price=models.DecimalField(max_digits=18,decimal_places=8,null=True,blank=True); exit_price=models.DecimalField(max_digits=18,decimal_places=8,null=True,blank=True); profit_loss=models.DecimalField(max_digits=18,decimal_places=8,default=0); risk=models.DecimalField(max_digits=18,decimal_places=8,default=0); status=models.CharField(max_length=24,default='open'); opened_at=models.DateTimeField(auto_now_add=True); closed_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['-opened_at']; indexes=[models.Index(fields=['symbol','status'])]
    @property
    def roi(self): return Decimal('0') if not self.entry_price else (self.profit_loss / self.entry_price) * Decimal('100')
