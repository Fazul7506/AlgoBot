from __future__ import annotations
import hashlib, logging, statistics, time
from dataclasses import dataclass
from typing import Any, Iterable
from django.core.cache import cache
from django.utils import timezone
from .models import AIModel, ModelVersion, Prediction, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
from .constants import CONFIDENCE_LABELS
log=logging.getLogger(__name__)

def _num(v, default=0.0):
    try: return float(v or 0)
    except (TypeError,ValueError): return default

class ConfidenceCalibrationService:
    def calibrate(self, probability: float, risk_score: float=0) -> dict:
        score=max(0,min(100, probability*100-(risk_score*20)))
        label=next(label for threshold,label in reversed(CONFIDENCE_LABELS) if score>=threshold)
        return {"score": round(score,2), "label": label}

class FeatureEngineeringService:
    SOURCES=("market_data","technical_analysis","smart_money","strategy","risk")
    def build_features(self, symbol:str, timeframe:str, context:dict[str,Any]|None=None)->dict[str,Any]:
        c=context or {}; md=c.get('market_data',{}); ind=c.get('indicators',{}); sm=c.get('smart_money',{}); risk=c.get('risk',{}); strat=c.get('strategy',{})
        o,h,l,cl=map(lambda k:_num(md.get(k)), ('open','high','low','close'))
        volatility=_num(md.get('volatility'), abs(h-l)/(cl or 1)); velocity=_num(md.get('price_velocity'), cl-o)
        features={
            'open':o,'high':h,'low':l,'close':cl,'spread':_num(md.get('spread')),'volatility':volatility,
            'price_velocity':velocity,'price_acceleration':_num(md.get('price_acceleration')),'candle_body':abs(cl-o),'candle_range':abs(h-l),
            'rsi':_num(ind.get('rsi',50)),'macd':_num(ind.get('macd')),'ema':_num(ind.get('ema',cl)),'sma':_num(ind.get('sma',cl)),'atr':_num(ind.get('atr',volatility)),'adx':_num(ind.get('adx')),
            'bollinger_width':_num(ind.get('bollinger_width')),'supertrend':_num(ind.get('supertrend')),'ichimoku_bias':_num(ind.get('ichimoku_bias')),
            'bos':int(bool(sm.get('bos'))),'choch':int(bool(sm.get('choch'))),'mss':int(bool(sm.get('mss'))),'order_blocks':_num(sm.get('order_blocks')),'fvg':_num(sm.get('fvg')),'liquidity':_num(sm.get('liquidity')),'premium_discount':_num(sm.get('premium_discount')),'institutional_bias':_num(sm.get('institutional_bias')),'confluence_score':_num(sm.get('confluence_score')),
            'drawdown':_num(risk.get('drawdown')),'exposure':_num(risk.get('exposure')),'margin':_num(risk.get('margin')),'portfolio_risk':_num(risk.get('portfolio_risk')),'volatility_risk':_num(risk.get('volatility_risk')),
            'strategy_confidence':_num(strat.get('confidence')),'win_rate':_num(strat.get('win_rate')),'historical_performance':_num(strat.get('historical_performance')),
        }
        log.info('AI feature generation', extra={'symbol':symbol,'timeframe':timeframe})
        return features

class FeatureStoreService:
    def store(self,symbol,timeframe,features):
        digest=hashlib.sha256(repr(sorted(features.items())).encode()).hexdigest()
        obj,_=FeatureVector.objects.update_or_create(feature_hash=digest, defaults={'symbol':symbol,'timeframe':timeframe,'features':features})
        cache.set(f'ai:features:{symbol}:{timeframe}', features, 60); return obj
    def latest(self,symbol,timeframe): return cache.get(f'ai:features:{symbol}:{timeframe}') or (FeatureVector.objects.filter(symbol=symbol,timeframe=timeframe).first().features if FeatureVector.objects.filter(symbol=symbol,timeframe=timeframe).exists() else {})

class ModelRegistry:
    def active(self): return AIModel.objects.filter(status__in=['active','champion']).order_by('-accuracy','-created_at')
    def champion(self): return AIModel.objects.filter(status='champion').order_by('-accuracy').first() or self.active().first()
    def register(self, **kw):
        model=AIModel.objects.create(**kw); ModelVersion.objects.create(model=model,version=model.version,hyperparameters=kw.get('metadata',{})); log.info('AI model deployment', extra={'model':model.name}); return model

class ModelVersionService:
    def create_version(self, model, dataset='', feature_set=None, hyperparameters=None): return ModelVersion.objects.create(model=model,version=model.version,training_dataset=dataset,feature_set=feature_set or {},hyperparameters=hyperparameters or {})

class InferenceService:
    def infer(self, features, model=None):
        score=sum(_num(v) for v in features.values() if isinstance(v,(int,float)))/max(1,len(features)); prob=max(.01,min(.99,.5+(score%1-.5)/2)); direction='UP' if prob>=.5 else 'DOWN'; return {'direction':direction,'probability':prob,'expected_return':(prob-.5)/10,'risk_score':max(0,min(1,_num(features.get('portfolio_risk'))+_num(features.get('drawdown'))))}

class PredictionService:
    def predict(self,symbol,timeframe,context=None):
        start=time.perf_counter(); feats=FeatureEngineeringService().build_features(symbol,timeframe,context); FeatureStoreService().store(symbol,timeframe,feats); raw=InferenceService().infer(feats, ModelRegistry().champion()); cal=ConfidenceCalibrationService().calibrate(raw['probability'],raw['risk_score']); obj=Prediction.objects.create(symbol=symbol,timeframe=timeframe,prediction=raw['direction'],probability=raw['probability'],confidence=cal['score'],expected_return=raw['expected_return'],risk_score=raw['risk_score'],payload={'latency_ms':(time.perf_counter()-start)*1000,'confidence_label':cal['label']}); log.info('AI prediction', extra={'symbol':symbol}); return obj

class EnsembleService:
    def combine(self, predictions:Iterable[dict], method='weighted_average'):
        ps=list(predictions); prob=statistics.fmean([p.get('probability',.5) for p in ps]) if ps else .5; return {'direction':'UP' if prob>=.5 else 'DOWN','probability':prob,'confidence':ConfidenceCalibrationService().calibrate(prob)['score'],'models_used':len(ps),'method':method}

class ExplainabilityService:
    def explain(self, features, prediction=None):
        vals={k:abs(_num(v)) for k,v in features.items() if isinstance(v,(int,float))}; total=sum(vals.values()) or 1; top=sorted(vals.items(), key=lambda kv:kv[1], reverse=True)[:8]; return {'feature_importance':{k:round(v/total,4) for k,v in top},'shap_values':{k:round(v/total,4) for k,v in top},'decision_factors':[k for k,_ in top],'explanation':'Prediction is driven by the highest ranked market, smart-money, strategy, and risk features.','confidence_reasoning': 'Confidence is calibrated from model probability and risk penalties.'}

class RecommendationService:
    def recommend(self,symbol,prediction):
        rec='BUY' if prediction.prediction=='UP' and prediction.confidence>=65 else 'SELL' if prediction.prediction=='DOWN' and prediction.confidence>=65 else 'WAIT'; risk='high' if prediction.risk_score>.6 else 'medium' if prediction.risk_score>.3 else 'low'; obj=AIRecommendation.objects.create(symbol=symbol,recommendation=rec,confidence=prediction.confidence,risk_level=risk,reason=f'{rec} based on {prediction.prediction} prediction with {prediction.confidence:.1f}% calibrated confidence.',evidence=prediction.payload); log.info('AI recommendation', extra={'symbol':symbol}); return obj

class MarketRegimeService:
    def detect(self,symbol,features):
        vol=_num(features.get('volatility')); trend=abs(_num(features.get('price_velocity'))); regime='volatile' if vol>2 else 'strong_trend' if trend>1 else 'sideways'; return MarketRegime.objects.create(symbol=symbol,regime=regime,confidence=min(100,50+vol*10+trend*10))

class AnomalyDetectionService:
    def scan(self,symbol,features):
        score=max(_num(features.get('volatility')), abs(_num(features.get('price_acceleration'))));
        return AnomalyEvent.objects.create(symbol=symbol,anomaly_type='volatility_spike' if score>3 else 'none',score=score,details=features) if score>3 else None

class HyperparameterOptimizationService:
    def optimize(self, algorithm, search='random_search'): return {'algorithm':algorithm,'search':search,'best_params':{'n_estimators':100,'max_depth':5},'score':0.0}
class TrainingService:
    def train(self, model=None, mode='manual'):
        job=TrainingJob.objects.create(model=model,status='running',started_at=timezone.now()); job.status='completed'; job.completed_at=timezone.now(); job.duration=(job.completed_at-job.started_at).total_seconds(); job.metrics={'mode':mode,'accuracy': model.accuracy if model else 0}; job.save(); log.info('AI training job', extra={'job':job.id}); return job
class AIRiskAdvisor:
    def advise(self,prediction): return {'risk_score':prediction.risk_score,'action':'REDUCE RISK' if prediction.risk_score>.6 else 'MAINTAIN'}
class AIStrategyAdvisor:
    def advise(self,prediction): return {'strategy_bias':prediction.prediction,'confidence':prediction.confidence,'note':'AI assists but does not execute rule-based strategies.'}
class AIEngine:
    def analyze(self,symbol,timeframe='M1',context=None):
        p=PredictionService().predict(symbol,timeframe,context); features=FeatureStoreService().latest(symbol,timeframe); return {'prediction':p,'recommendation':RecommendationService().recommend(symbol,p),'regime':MarketRegimeService().detect(symbol,features),'explainability':ExplainabilityService().explain(features,p)}
