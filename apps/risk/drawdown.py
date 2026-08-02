from decimal import Decimal
from .models import DrawdownHistory
class DrawdownService:
    def record(self,user,balance,equity):
        balance=Decimal(str(balance)); equity=Decimal(str(equity)); dd=max(balance-equity,Decimal('0')); pct=dd/balance if balance else Decimal('0')
        return DrawdownHistory.objects.create(user=user,balance=balance,equity=equity,drawdown=dd,drawdown_percent=pct)
    def state(self,user,profile=None):
        latest=DrawdownHistory.objects.filter(user=user).first(); pct=latest.drawdown_percent if latest else Decimal('0'); limit=getattr(profile,'max_drawdown',Decimal('0.10'))
        if pct>=limit: level='hard_stop'
        elif pct>=limit*Decimal('0.75'): level='soft_stop'
        elif pct>=limit*Decimal('0.50'): level='warning'
        else: level='normal'
        return {'level':level,'drawdown_percent':pct,'manual_override':False,'recovery_mode':level in ('soft_stop','hard_stop')}
