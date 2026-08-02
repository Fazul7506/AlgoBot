from decimal import Decimal
from django.db.models import Sum
from .models import Exposure
class ExposureService:
    def update(self,user,symbol,market,value,total_equity):
        pct=Decimal(str(value or 0))/Decimal(str(total_equity or 1))
        obj,_=Exposure.objects.update_or_create(user=user,symbol=symbol,market=market or '',defaults={'exposure_value':value,'percentage':pct})
        return obj
    def summary(self,user):
        qs=Exposure.objects.filter(user=user); return {'overall':qs.aggregate(total=Sum('exposure_value'))['total'] or 0,'positions':list(qs.values('symbol','market','exposure_value','percentage'))}
