from .models import Indicator, IndicatorValue
class IndicatorRepository:
    def get_or_create_indicator(self,name,category='momentum',parameters=None):
        return Indicator.objects.get_or_create(name=name, defaults={'category':category,'parameters':parameters or {}})[0]
    def save_value(self,symbol,timeframe,indicator,value,metadata=None,timestamp=None):
        data={'symbol':symbol,'timeframe':timeframe,'indicator':indicator,'value':value,'metadata':metadata or {}}
        if timestamp: data['timestamp']=timestamp
        return IndicatorValue.objects.create(**data)
    def latest(self,symbol,timeframe,indicator=None):
        qs=IndicatorValue.objects.filter(symbol=symbol,timeframe=timeframe)
        if indicator: qs=qs.filter(indicator__name=indicator)
        return qs.order_by('-timestamp')
