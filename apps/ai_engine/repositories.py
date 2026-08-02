from .models import AIModel, Prediction, FeatureVector, AIRecommendation, MarketRegime
class AIModelRepository:
    def active(self): return AIModel.objects.filter(status__in=['active','champion'])
class PredictionRepository:
    def latest(self, symbol, timeframe=None):
        qs=Prediction.objects.filter(symbol=symbol); qs=qs.filter(timeframe=timeframe) if timeframe else qs; return qs.first()
class FeatureVectorRepository:
    def latest(self, symbol, timeframe): return FeatureVector.objects.filter(symbol=symbol,timeframe=timeframe).first()
class RecommendationRepository:
    def latest(self, symbol): return AIRecommendation.objects.filter(symbol=symbol).first()
class MarketRegimeRepository:
    def latest(self, symbol): return MarketRegime.objects.filter(symbol=symbol).first()
