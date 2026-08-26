import asyncio, logging, time
from django.utils import timezone
from .registry import registry
from .repositories import StrategyRepository, StrategyExecutionRepository, StrategySignalRepository, StrategyPerformanceRepository
from .validator import StrategyValidationService
log=logging.getLogger(__name__)

class LiveMarketContextService:
    """Fetch broker candles and build a non-empty, model-compatible live context."""
    def _run(self, awaitable): return asyncio.run(awaitable)
    def _granularity(self, timeframe): return {'M1':60,'M5':300,'M15':900,'M30':1800,'H1':3600,'H4':14400,'D1':86400}.get(str(timeframe).upper(),60)
    @staticmethod
    def _rsi(closes, period=14):
        if len(closes) <= period: return 50.0
        gains=[]; losses=[]
        for a,b in zip(closes[-period-1:-1],closes[-period:]):
            delta=b-a; gains.append(max(delta,0)); losses.append(max(-delta,0))
        avg_gain=sum(gains)/period; avg_loss=sum(losses)/period
        if avg_loss == 0: return 100.0 if avg_gain else 50.0
        return 100.0-(100.0/(1.0+(avg_gain/avg_loss)))
    def build(self, config):
        account=getattr(config,'broker_account',None)
        if account is None or getattr(account,'status',None)!='active': raise RuntimeError('An active broker account is required for autonomous strategy execution')
        from apps.brokers.services import BrokerRegistry
        adapter=BrokerRegistry().adapter(account.broker,account)
        history=self._run(adapter.get_chart_history(config.symbol,mode='candles',count=200,granularity=self._granularity(config.timeframe)))
        items=history.get('items') or []; candles=[]
        for item in items:
            try: candles.append({'open':float(item['open']),'high':float(item['high']),'low':float(item['low']),'close':float(item['close']),'volume':float(item.get('volume',0) or 0),'epoch':int(item.get('epoch',0) or 0)})
            except (KeyError,TypeError,ValueError): continue
        if len(candles)<25: raise RuntimeError(f'Insufficient live broker candle history for {config.symbol} {config.timeframe}: {len(candles)} usable candles')
        from trading.ai.features.simple_indicators import compute_basic_features
        rows=compute_basic_features(candles); latest=rows[-1]; current=candles[-1]; closes=[c['close'] for c in candles]
        trend='up' if latest.get('sma5') is not None and latest.get('sma20') is not None and latest['sma5']>latest['sma20'] else 'down' if latest.get('sma5') is not None and latest.get('sma20') is not None and latest['sma5']<latest['sma20'] else 'sideways'
        market_data={'symbol':config.symbol,'open':current['open'],'high':current['high'],'low':current['low'],'close':current['close'],'volume':current['volume'],'epoch':current['epoch'],'source':'live_broker'}
        indicator_data={'sma5':latest.get('sma5'),'sma20':latest.get('sma20'),'ema10':latest.get('ema10'),'ret1':latest.get('ret1',0.0),'range':latest.get('range',0.0),'rsi':self._rsi(closes),'trend':trend,'source':'live_broker'}
        return market_data,indicator_data,{'source':'live_broker','candles':candles,'candles_used':len(candles),'timeframe':config.timeframe,'latest_epoch':current['epoch']}

class StrategyService:
    def sync_catalog(self): return [StrategyRepository().create_or_update_catalog(cls) for cls in registry.all().values()]

class StrategyExecutionService:
    def run_configuration(self, config, market_data=None, indicator_data=None):
        start=time.perf_counter(); execution=StrategyExecutionRepository().create(strategy=config.strategy,configuration=config,symbol=config.symbol,timeframe=config.timeframe,status='running')
        try:
            if market_data is None or indicator_data is None: market_data,indicator_data,handoff=LiveMarketContextService().build(config)
            else: handoff={'source':'caller_supplied','timeframe':config.timeframe}
            if not market_data or market_data.get('close') is None: raise RuntimeError('No live market price was supplied to strategy execution')
            cls=registry.get(config.strategy.slug); strat=cls(config,market_data,indicator_data); strat.initialize(); strat.validate(); result=strat.execute(); StrategyValidationService().validate_signal(result['signal'])
            ai_enabled=(config.parameters or {}).get('ai_ensemble_enabled',True); ai_consensus=None
            if ai_enabled:
                from apps.ai_engine.services import PredictionService,RecommendationService
                ai_context={'market_data':market_data,'indicators':indicator_data,'strategy':{'confidence':result.get('confidence',0)},'risk':(config.parameters or {}).get('risk',{}),'candles':handoff.get('candles',[])}
                prediction=PredictionService().predict(config.symbol,config.timeframe,ai_context); recommendation=RecommendationService().recommend(config.symbol,prediction); ai_consensus=(prediction.payload or {}).get('consensus') or {}
                result={**result,'strategy_signal':result['signal'],'strategy_confidence':result.get('confidence',0),'signal':recommendation.recommendation if recommendation.recommendation in {'BUY','SELL'} else 'HOLD','confidence':recommendation.confidence,'ai_consensus':ai_consensus,'ai_prediction_id':prediction.pk,'ai_recommendation_id':recommendation.pk,'market_data_handoff':{k:v for k,v in handoff.items() if k!='candles'}}
            execution.signal=result['signal']; execution.confidence=result['confidence']; execution.status='completed'; execution.completed_at=timezone.now(); execution.latency_ms=(time.perf_counter()-start)*1000; execution.context=result; execution.save()
            StrategySignalRepository().create(strategy=config.strategy,configuration=config,symbol=config.symbol,signal=result['signal'],confidence=result['confidence'],entry_price=result.get('entry_price'),stop_loss=result.get('stop_loss'),take_profit=result.get('take_profit'),metadata=result)
            log.info('Strategy execution completed',extra={'strategy':config.strategy.slug,'signal':result['signal'],'ai_ensemble':bool(ai_consensus),'market_source':handoff.get('source')}); return execution
        except Exception as exc:
            execution.status='failed'; execution.error=str(exc); execution.completed_at=timezone.now(); execution.latency_ms=(time.perf_counter()-start)*1000; execution.save(); log.exception('Strategy execution failed'); return execution

class StrategyPerformanceService:
    def recalculate(self,strategy):
        perf=StrategyPerformanceRepository().for_strategy(strategy); qs=strategy.executions.filter(status='completed').exclude(signal='HOLD'); perf.total_trades=qs.count(); perf.wins=strategy.executions.filter(context__outcome='win').count(); perf.losses=strategy.executions.filter(context__outcome='loss').count(); perf.win_rate=(perf.wins/perf.total_trades*100) if perf.total_trades else 0; perf.last_updated=timezone.now(); perf.save(); return perf
class StrategyOptimizationService: pass
class StrategyValidationService(StrategyValidationService): pass
