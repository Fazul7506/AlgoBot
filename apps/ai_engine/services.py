from __future__ import annotations
import hashlib, logging, time
from typing import Any, Iterable
from django.core.cache import cache
from django.utils import timezone
from .models import AIModel, ModelVersion, Prediction, FeatureVector, TrainingJob, AIRecommendation, MarketRegime, AnomalyEvent
from .constants import CONFIDENCE_LABELS
from trading.ai.candlestick_features import FEATURE_NAMES, extract_candlestick_features
log=logging.getLogger(__name__)

def _num(v, default=0.0):
    try: return float(v or 0)
    except (TypeError,ValueError): return default

def _decision(value):
    value=str(value or '').upper()
    return {'UP':'BUY','LONG':'BUY','DOWN':'SELL','SHORT':'SELL','WAIT':'AVOID','HOLD':'AVOID','NO_MODELS':'AVOID','AI_ERROR':'AVOID','DO NOT TRADE':'AVOID'}.get(value,value if value in {'BUY','SELL','AVOID'} else 'AVOID')

class ConfidenceCalibrationService:
    def calibrate(self, probability: float, risk_score: float=0) -> dict:
        score=max(0,min(100, probability*100-(risk_score*20)))
        label=next(label for threshold,label in reversed(CONFIDENCE_LABELS) if score>=threshold)
        return {"score": round(score,2), "label": label}

class FeatureEngineeringService:
    SOURCES=("market_data","technical_analysis","smart_money","strategy","risk","candlestick_price_action")
    def build_features(self, symbol:str, timeframe:str, context:dict[str,Any]|None=None)->dict[str,Any]:
        c=context or {}; md=c.get('market_data',{}); ind=c.get('indicators',{}); sm=c.get('smart_money',{}); risk=c.get('risk',{}); strat=c.get('strategy',{})
        o,h,l,cl=map(lambda k:_num(md.get(k)), ('open','high','low','close'))
        volatility=_num(md.get('volatility'), abs(h-l)/(cl or 1)); velocity=_num(md.get('price_velocity'), cl-o)
        features={'open':o,'high':h,'low':l,'close':cl,'spread':_num(md.get('spread')),'volatility':volatility,'price_velocity':velocity,'price_acceleration':_num(md.get('price_acceleration')),'candle_body':abs(cl-o),'candle_range':abs(h-l),'rsi':_num(ind.get('rsi',50)),'macd':_num(ind.get('macd')),'ema':_num(ind.get('ema',cl)),'sma':_num(ind.get('sma',cl)),'atr':_num(ind.get('atr',volatility)),'adx':_num(ind.get('adx')),'bollinger_width':_num(ind.get('bollinger_width')),'supertrend':_num(ind.get('supertrend')),'ichimoku_bias':_num(ind.get('ichimoku_bias')),'bos':int(bool(sm.get('bos'))),'choch':int(bool(sm.get('choch'))),'mss':int(bool(sm.get('mss'))),'order_blocks':_num(sm.get('order_blocks')),'fvg':_num(sm.get('fvg')),'liquidity':_num(sm.get('liquidity')),'premium_discount':_num(sm.get('premium_discount')),'institutional_bias':_num(sm.get('institutional_bias')),'confluence_score':_num(sm.get('confluence_score')),'drawdown':_num(risk.get('drawdown')),'exposure':_num(risk.get('exposure')),'margin':_num(risk.get('margin')),'portfolio_risk':_num(risk.get('portfolio_risk')),'volatility_risk':_num(risk.get('volatility_risk')),'strategy_confidence':_num(strat.get('confidence')),'win_rate':_num(strat.get('win_rate')),'historical_performance':_num(strat.get('historical_performance'))}
        candles=c.get('candles') or md.get('candles')
        if candles and len(candles)>=25:
            try: features.update(extract_candlestick_features(candles[-60:]))
            except Exception as exc: log.warning('Candlestick feature extraction failed', extra={'symbol':symbol,'error':str(exc)})
        else:
            # Preserve the model contract even when live inference has no candle window.
            features.update({name:0.0 for name in FEATURE_NAMES})
        return features

class FeatureStoreService:
    def store(self,symbol,timeframe,features):
        digest=hashlib.sha256(repr(sorted(features.items())).encode()).hexdigest(); obj,_=FeatureVector.objects.update_or_create(feature_hash=digest, defaults={'symbol':symbol,'timeframe':timeframe,'features':features}); cache.set(f'ai:features:{symbol}:{timeframe}', features, 60); return obj
    def latest(self,symbol,timeframe):
        cached=cache.get(f'ai:features:{symbol}:{timeframe}')
        if cached: return cached
        obj=FeatureVector.objects.filter(symbol=symbol,timeframe=timeframe).order_by('-id').first(); return obj.features if obj else {}

class ModelRegistry:
    def active(self): return AIModel.objects.filter(status__in=['active','champion']).order_by('-accuracy','-created_at')
    def champion(self): return AIModel.objects.filter(status='champion').order_by('-accuracy').first() or self.active().first()
    def register(self, **kw):
        model=AIModel.objects.create(**kw); ModelVersion.objects.create(model=model,version=model.version,hyperparameters=kw.get('metadata',{})); return model

class ModelVersionService:
    def create_version(self, model, dataset='', feature_set=None, hyperparameters=None): return ModelVersion.objects.create(model=model,version=model.version,training_dataset=dataset,feature_set=feature_set or {},hyperparameters=hyperparameters or {})

class InferenceService:
    def _trained_ensemble(self, symbol, timeframe):
        try:
            from trading.ai.ensemble import EnsemblePredictor
            return EnsemblePredictor(symbol, timeframe)
        except Exception as exc:
            log.warning('AI ensemble unavailable', extra={'symbol':symbol,'error':str(exc)}); return None

    def infer(self, features, model=None, symbol=None, timeframe='M1'):
        ensemble=self._trained_ensemble(symbol, timeframe) if symbol else None
        if ensemble and ensemble.models:
            try:
                import numpy as np
                # Tree models are trained on the exact ordered FEATURE_NAMES contract.
                vector=np.array([[ _num(features.get(name, 0.0)) for name in FEATURE_NAMES ]], dtype=float)
                result=ensemble.predict(vector)
                direction=_decision(result.get('direction'))
                prob=float(result.get('probability',0))
                consensus={'decision': direction,'probability': round(prob,6),'confidence': round(float(result.get('confidence',prob*100)),2),'agreement': round(float(result.get('agreement',0)),6),'disagreement': round(float(result.get('disagreement',0)),6),'models_used': int(result.get('models_used',0)),'model_types': result.get('model_types',[]),'method': result.get('method','weighted_average'),'model_outputs': result.get('model_outputs',result.get('predictions',[]))}
                return {'direction':direction,'probability':prob,'expected_return':(prob-.5)/10,'risk_score':max(0,min(1,_num(features.get('portfolio_risk'))+_num(features.get('drawdown')))),'models_used':consensus['models_used'],'model_types':consensus['model_types'],'consensus':consensus,'source':'trained_ensemble'}
            except Exception as exc:
                log.exception('AI ensemble inference failed', extra={'symbol':symbol}); return {'direction':'AVOID','probability':0.0,'expected_return':0.0,'risk_score':1.0,'models_used':0,'error':str(exc),'source':'trained_ensemble','consensus':{'decision':'AVOID','probability':0.0,'confidence':0.0,'models_used':0,'reason':'ensemble_inference_error'}}
        return {'direction':'AVOID','probability':0.0,'expected_return':0.0,'risk_score':1.0,'models_used':0,'model_types':[],'source':'no_trained_model','consensus':{'decision':'AVOID','probability':0.0,'confidence':0.0,'models_used':0,'reason':'no_trained_model'}}

class PredictionService:
    def predict(self,symbol,timeframe,context=None):
        start=time.perf_counter(); feats=FeatureEngineeringService().build_features(symbol,timeframe,context); FeatureStoreService().store(symbol,timeframe,feats); raw=InferenceService().infer(feats, ModelRegistry().champion(), symbol, timeframe); cal=ConfidenceCalibrationService().calibrate(raw['probability'],raw['risk_score']); consensus=raw.get('consensus',{}); obj=Prediction.objects.create(symbol=symbol,timeframe=timeframe,prediction=raw['direction'],probability=raw['probability'],confidence=cal['score'],expected_return=raw['expected_return'],risk_score=raw['risk_score'],payload={'latency_ms':(time.perf_counter()-start)*1000,'confidence_label':cal['label'],'models_used':raw.get('models_used',0),'model_types':raw.get('model_types',[]),'source':raw.get('source'),'consensus':consensus,'feature_set':list(FEATURE_NAMES)}); return obj

class EnsembleService:
    def combine(self, predictions:Iterable[dict], method='weighted_average'):
        ps=list(predictions)
        if not ps: return {'decision':'AVOID','direction':'AVOID','probability':0.0,'confidence':0.0,'models_used':0,'method':method,'agreement':0.0}
        weights=[max(0.0,_num(p.get('weight',1.0),1.0)) for p in ps]; total=sum(weights) or 1.0
        scores={'BUY':0.0,'SELL':0.0,'AVOID':0.0}
        for p,w in zip(ps,weights):
            d=_decision(p.get('decision',p.get('direction'))); conf=max(0,min(1,_num(p.get('confidence',p.get('probability',0)))/(100 if _num(p.get('confidence',0))>1 else 1))); scores[d]+=w*conf
        normalized={k:v/total for k,v in scores.items()}; decision=max(normalized,key=normalized.get); agreement=normalized[decision]; confidence=agreement*100
        if agreement < 0.60: decision='AVOID'
        return {'decision':decision,'direction':decision,'probability':round(agreement if decision!='AVOID' else max(normalized.values()),6),'confidence':round(confidence,2),'models_used':len(ps),'method':method,'agreement':round(agreement,6),'scores':normalized}

class ExplainabilityService:
    def explain(self, features, prediction=None):
        vals={k:abs(_num(v)) for k,v in features.items() if isinstance(v,(int,float))}; total=sum(vals.values()) or 1; top=sorted(vals.items(), key=lambda kv:kv[1], reverse=True)[:12]; return {'feature_importance':{k:round(v/total,4) for k,v in top},'shap_values':{k:round(v/total,4) for k,v in top},'decision_factors':[k for k,_ in top],'explanation':'The explanation ranks quantitative market, candlestick, technical, strategy and risk features. A recommendation is actionable only when a trained model passes the configured confidence gate.','confidence_reasoning':'Confidence is calibrated from model probability and risk penalties.'}

class RecommendationService:
    MIN_CONFIDENCE=65.0
    MIN_MODELS=1
    def recommend(self,symbol,prediction):
        payload=prediction.payload or {}; consensus=payload.get('consensus') or {}; decision=_decision(consensus.get('decision',prediction.prediction)); confidence=float(consensus.get('confidence',prediction.confidence) or 0); models=int(consensus.get('models_used',payload.get('models_used',0)) or 0)
        actionable=decision in {'BUY','SELL'} and confidence>=self.MIN_CONFIDENCE and models>=self.MIN_MODELS
        rec=decision if actionable else 'WAIT'; risk='high' if prediction.risk_score>.6 else 'medium' if prediction.risk_score>.3 else 'low'
        evidence={**payload,'consensus':{**consensus,'decision':decision,'confidence':confidence,'actionable':actionable}}
        return AIRecommendation.objects.create(symbol=symbol,recommendation=rec,confidence=confidence,risk_level=risk,reason=f'{rec} based on ensemble consensus {decision} with {confidence:.1f}% confidence across {models} model(s).',evidence=evidence)

class ConsensusDecisionGate:
    MIN_CONFIDENCE=65.0
    def validate(self, prediction, intended_direction=None):
        payload=prediction.payload or {}; consensus=payload.get('consensus') or {}; decision=_decision(consensus.get('decision',prediction.prediction)); confidence=float(consensus.get('confidence',prediction.confidence) or 0); models=int(consensus.get('models_used',0) or 0)
        if decision not in {'BUY','SELL'}: return False, 'Ensemble consensus is not actionable'
        if confidence < self.MIN_CONFIDENCE: return False, f'Ensemble confidence {confidence:.2f}% below {self.MIN_CONFIDENCE:.2f}% gate'
        if models < 1: return False, 'No trained ensemble models available'
        if intended_direction and _decision(intended_direction)!=decision: return False, 'Order direction conflicts with ensemble consensus'
        return True, 'Ensemble consensus approved'

class MarketRegimeService:
    def detect(self,symbol,features):
        vol=_num(features.get('volatility')); trend=abs(_num(features.get('trend_score',features.get('price_velocity')))); chop=_num(features.get('chop_score')); regime='volatile' if vol>2 else 'choppy' if chop>.7 else 'strong_trend' if trend>.2 else 'sideways'; return MarketRegime.objects.create(symbol=symbol,regime=regime,confidence=min(100,50+vol*10+trend*10))
class AnomalyDetectionService:
    def scan(self,symbol,features):
        score=max(_num(features.get('volatility')), abs(_num(features.get('price_acceleration')))); return AnomalyEvent.objects.create(symbol=symbol,anomaly_type='volatility_spike' if score>3 else 'none',score=score,details=features) if score>3 else None
class HyperparameterOptimizationService:
    def optimize(self, algorithm, search='random_search'): return {'algorithm':algorithm,'search':search,'best_params':{'n_estimators':100,'max_depth':5},'score':0.0}
class TrainingService:
    def train(self, model=None, mode='manual', symbol=None, timeframe='M1', min_accuracy=0.52):
        from .training import MarketModelTrainer
        if symbol:
            metrics=MarketModelTrainer().train_symbol(symbol,timeframe,min_accuracy)
            return TrainingJob.objects.filter(metrics__symbol=symbol).order_by('-started_at').first()
        results=MarketModelTrainer().train_active_symbols(timeframe,min_accuracy)
        return TrainingJob.objects.create(status='completed',started_at=timezone.now(),completed_at=timezone.now(),metrics={'mode':mode,'results':results,'feature_set':list(FEATURE_NAMES)})
class AIRiskAdvisor:
    def advise(self,prediction): return {'risk_score':prediction.risk_score,'action':'REDUCE RISK' if prediction.risk_score>.6 else 'MAINTAIN'}
class AIStrategyAdvisor:
    def advise(self,prediction): return {'strategy_bias':prediction.prediction,'confidence':prediction.confidence,'note':'AI assists but does not replace the configured strategy and risk engine.'}
class AIEngine:
    def analyze(self,symbol,timeframe='M1',context=None):
        p=PredictionService().predict(symbol,timeframe,context); features=FeatureStoreService().latest(symbol,timeframe); return {'prediction':p,'recommendation':RecommendationService().recommend(symbol,p),'regime':MarketRegimeService().detect(symbol,features),'explainability':ExplainabilityService().explain(features,p)}
