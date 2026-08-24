from rest_framework import viewsets, permissions, decorators, response
from django.shortcuts import render
from . import models
from .serializers import *
from .services import SmartMoneyEngine

class SmartMoneyDashboardViewSet(viewsets.ViewSet):
    permission_classes=[permissions.IsAuthenticated]
    @decorators.action(detail=False,methods=['post'])
    def analyze(self,request):
        s=AnalysisRequestSerializer(data=request.data); s.is_valid(raise_exception=True); d=s.validated_data
        return response.Response(SmartMoneyEngine().analyze(d['symbol'],d['timeframe'],d['candles']))
    def list(self,request): return response.Response({'engine':'smart_money','status':'ready'})

def page(request, template='smart_money/dashboard.html'): return render(request, template)

def _vs(model, serializer):
    return type(model.__name__+'ViewSet',(viewsets.ReadOnlyModelViewSet,),{'queryset':model.objects.all(),'serializer_class':serializer,'permission_classes':[permissions.IsAuthenticated]})

class LiquidityZoneViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=LiquidityZoneSerializer
    permission_classes=[permissions.IsAuthenticated]
    def get_queryset(self):
        qs=models.LiquidityZone.objects.all().order_by('-id')
        symbol=self.request.query_params.get('symbol')
        timeframe=self.request.query_params.get('timeframe')
        if symbol: qs=qs.filter(symbol=symbol)
        if timeframe: qs=qs.filter(timeframe=timeframe)
        return qs[:100]

MarketStructureViewSet=_vs(models.MarketStructure,MarketStructureSerializer)
OrderBlockViewSet=_vs(models.OrderBlock,OrderBlockSerializer)
BreakerBlockViewSet=_vs(models.BreakerBlock,BreakerBlockSerializer)
FairValueGapViewSet=_vs(models.FairValueGap,FairValueGapSerializer)
LiquiditySweepViewSet=_vs(models.LiquiditySweep,LiquiditySweepSerializer)
PremiumDiscountZoneViewSet=_vs(models.PremiumDiscountZone,PremiumDiscountZoneSerializer)
TradingSessionViewSet=_vs(models.TradingSession,TradingSessionSerializer)
InstitutionalBiasViewSet=_vs(models.InstitutionalBias,InstitutionalBiasSerializer)
