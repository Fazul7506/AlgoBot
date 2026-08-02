from rest_framework import serializers
from .models import MarketStructure,OrderBlock,BreakerBlock,MitigationBlock,FairValueGap,LiquidityZone,LiquiditySweep,PremiumDiscountZone,TradingSession,InstitutionalBias
for_model=(MarketStructure,OrderBlock,BreakerBlock,MitigationBlock,FairValueGap,LiquidityZone,LiquiditySweep,PremiumDiscountZone,TradingSession,InstitutionalBias)
def make_serializer(model):
    class S(serializers.ModelSerializer):
        class Meta: fields='__all__'
    S.Meta.model=model; S.__name__=model.__name__+'Serializer'; return S
MarketStructureSerializer,OrderBlockSerializer,BreakerBlockSerializer,MitigationBlockSerializer,FairValueGapSerializer,LiquidityZoneSerializer,LiquiditySweepSerializer,PremiumDiscountZoneSerializer,TradingSessionSerializer,InstitutionalBiasSerializer=[make_serializer(m) for m in for_model]
class AnalysisRequestSerializer(serializers.Serializer):
    symbol=serializers.CharField(max_length=40); timeframe=serializers.CharField(max_length=12); candles=serializers.ListField(child=serializers.DictField(),min_length=3)
