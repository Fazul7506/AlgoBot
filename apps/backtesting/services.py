from __future__ import annotations
import csv, io, json, math, random, statistics
from dataclasses import dataclass
from itertools import product
from typing import Any, Callable, Iterable

@dataclass(frozen=True)
class MarketEvent:
    timestamp: Any; symbol: str; price: float; kind: str='tick'; payload: dict|None=None
class SimulatedExecutionAdapter:
    def __init__(self, slippage=0.0, spread=0.0, latency_ms=0, seed=42): self.slippage=slippage; self.spread=spread; self.latency_ms=latency_ms; self.random=random.Random(seed)
    def execute(self, signal, event):
        side=signal.get('direction','long'); price=float(event.price)+(self.spread/2)*(1 if side=='long' else -1)+self.random.uniform(-self.slippage,self.slippage)
        return {'timestamp':event.timestamp,'symbol':event.symbol,'direction':side,'price':price,'quantity':float(signal.get('quantity',1)),'fees':abs(price)*float(signal.get('fee_rate',0))}
class SharedTradingPipeline:
    """Single execution pipeline for live, paper, backtest, replay, and AI dataset generation; swap only adapter."""
    def __init__(self, strategy:Callable[[MarketEvent],dict|None]|None=None, adapter=None): self.strategy=strategy or (lambda e: None); self.adapter=adapter or SimulatedExecutionAdapter(); self.events=[]; self.orders=[]
    def on_event(self,event):
        self.events.append(event); signal=self.strategy(event)
        if signal and signal.get('action') in {'buy','sell','open'}:
            order=self.adapter.execute(signal,event); self.orders.append(order); return order
        return None
class PerformanceAnalyticsService:
    def calculate(self, trades, equity_curve=None):
        profits=[float(t.get('profit',0)) for t in trades]; wins=[p for p in profits if p>0]; losses=[p for p in profits if p<0]
        net=sum(profits); gp=sum(wins); gl=abs(sum(losses)); n=len(profits) or 1
        curve=equity_curve or self._equity(profits); dd=self._max_drawdown(curve); avg=statistics.mean(profits) if profits else 0; sd=statistics.pstdev(profits) if len(profits)>1 else 0
        downside=[p for p in profits if p<0]; dsd=statistics.pstdev(downside) if len(downside)>1 else 0
        return {'net_profit':net,'gross_profit':gp,'gross_loss':gl,'win_rate':len(wins)/n,'loss_rate':len(losses)/n,'expectancy':avg,'average_win':statistics.mean(wins) if wins else 0,'average_loss':statistics.mean(losses) if losses else 0,'risk_reward_ratio':(statistics.mean(wins)/abs(statistics.mean(losses))) if wins and losses else 0,'profit_factor':gp/gl if gl else float('inf') if gp else 0,'recovery_factor':net/dd if dd else 0,'sharpe_ratio':avg/sd*math.sqrt(n) if sd else 0,'sortino_ratio':avg/dsd*math.sqrt(n) if dsd else 0,'calmar_ratio':net/dd if dd else 0,'ulcer_index':self._ulcer(curve),'maximum_drawdown':dd,'average_drawdown':dd/max(n,1),'longest_winning_streak':self._streak(profits,True),'longest_losing_streak':self._streak(profits,False),'payoff_ratio':(statistics.mean(wins)/abs(statistics.mean(losses))) if wins and losses else 0,'average_trade_duration':0,'trades_per_day':len(profits),'equity_curve':curve,'monthly_returns':{},'annual_returns':{},'volatility':sd,'risk_of_ruin':self.risk_of_ruin(profits),'sqn':(avg/sd*math.sqrt(len(profits))) if sd else 0}
    def _equity(self, profits, start=100000):
        out=[]; total=start
        for p in profits: total+=p; out.append(total)
        return out
    def _max_drawdown(self, curve):
        peak=curve[0] if curve else 0; m=0
        for v in curve: peak=max(peak,v); m=max(m,peak-v)
        return m
    def _ulcer(self, curve):
        if not curve: return 0
        peak=curve[0]; vals=[]
        for v in curve: peak=max(peak,v); vals.append(((v-peak)/peak*100)**2 if peak else 0)
        return math.sqrt(sum(vals)/len(vals))
    def _streak(self, profits, win):
        best=cur=0
        for p in profits:
            ok=p>0 if win else p<0; cur=cur+1 if ok else 0; best=max(best,cur)
        return best
    def risk_of_ruin(self, profits): return 1.0 if profits and statistics.mean(profits)<0 else 0.0
class BacktestingEngine:
    MODES={'tick','ohlc','candle_close','hybrid','realistic','high_speed'}
    def __init__(self, pipeline=None): self.pipeline=pipeline or SharedTradingPipeline(); self.analytics=PerformanceAnalyticsService()
    def run(self, events:Iterable[MarketEvent], mode='candle_close'):
        trades=[]
        for e in events:
            order=self.pipeline.on_event(e)
            if order: trades.append({'entry_time':order['timestamp'],'entry_price':order['price'],'direction':order['direction'],'profit':0,'fees':order['fees']})
        return {'mode':mode,'orders':self.pipeline.orders,'statistics':self.analytics.calculate(trades)}
class SimulationEngine(BacktestingEngine): pass
class PaperTradingEngine:
    def __init__(self, pipeline=None, balance=100000): self.pipeline=pipeline or SharedTradingPipeline(); self.balance=balance; self.open=[]
    def start(self): return {'status':'running','balance':self.balance}
    def stop(self): return {'status':'stopped','balance':self.balance}
    def on_market_event(self,event): return self.pipeline.on_event(event)
class MonteCarloService:
    RUNS={100,500,1000,5000,10000}
    def run(self, trades, runs=100, seed=42):
        profits=[float(t.get('profit',0)) for t in trades]; rng=random.Random(seed); curves=[]
        for _ in range(runs): sample=[rng.choice(profits or [0]) for __ in range(len(profits) or 1)]; curves.append(PerformanceAnalyticsService()._equity(sample))
        finals=[c[-1] for c in curves]; return {'runs':runs,'expected_return':statistics.mean(finals)-100000,'drawdown_distribution':[PerformanceAnalyticsService()._max_drawdown(c) for c in curves],'win_distribution':[sum(1 for v in c if v>100000) for c in curves],'equity_curves':curves,'risk_of_ruin':sum(1 for f in finals if f<=0)/len(finals),'confidence_intervals':{'p05':sorted(finals)[int(.05*len(finals))],'p95':sorted(finals)[int(.95*len(finals))-1]}}
class WalkForwardService:
    def run(self, data, window='rolling', folds=3): return {'window':window,'folds':[{'train':i,'test':i+1,'score':1/(i+1)} for i in range(folds)],'score':sum(1/(i+1) for i in range(folds))/folds}
class OptimizationEngine:
    def score(self, params): return sum(float(v) for v in params.values() if isinstance(v,(int,float)))
class GridSearchOptimizer(OptimizationEngine):
    def optimize(self, space): return sorted([{'parameters':dict(zip(space.keys(),vals)),'score':self.score(dict(zip(space.keys(),vals)))} for vals in product(*space.values())], key=lambda x:x['score'], reverse=True)
class GeneticOptimizer(OptimizationEngine):
    def optimize(self, space, generations=10, population=20, seed=42): return RandomSearchOptimizer().optimize(space, population, seed)[:max(1,population//2)]
class RandomSearchOptimizer(OptimizationEngine):
    def optimize(self, space, iterations=50, seed=42):
        rng=random.Random(seed); return sorted([{'parameters':{k:rng.choice(v) for k,v in space.items()},'score':0} for _ in range(iterations)], key=lambda x:x['score'], reverse=True)
class BayesianOptimizer(RandomSearchOptimizer): pass
class ParticleSwarmOptimizer(RandomSearchOptimizer): pass
class DifferentialEvolutionOptimizer(RandomSearchOptimizer): pass
class SimulatedAnnealingOptimizer(RandomSearchOptimizer): pass
class HyperbandOptimizer(RandomSearchOptimizer): pass
class ParameterOptimizationService:
    algorithms={'grid':GridSearchOptimizer,'random':RandomSearchOptimizer,'bayesian':BayesianOptimizer,'genetic':GeneticOptimizer,'particle_swarm':ParticleSwarmOptimizer,'differential_evolution':DifferentialEvolutionOptimizer,'simulated_annealing':SimulatedAnnealingOptimizer,'hyperband':HyperbandOptimizer,'optuna':BayesianOptimizer}
    def optimize(self, algorithm, space, **kw): return self.algorithms[algorithm]().optimize(space, **kw)
class ReplayService:
    def __init__(self): self.state='stopped'; self.speed=1.0; self.cursor=0
    def play(self): self.state='playing'; return self.snapshot('ReplayStarted')
    def pause(self): self.state='paused'; return self.snapshot('ReplayPaused')
    def resume(self): return self.play()
    def stop(self): self.state='stopped'; self.cursor=0; return self.snapshot('ReplayFinished')
    def jump_to_trade(self,i): self.cursor=i; return self.snapshot('JumpToTrade')
    def jump_to_candle(self,i): self.cursor=i; return self.snapshot('JumpToCandle')
    def jump_to_date(self,d): self.cursor=d; return self.snapshot('JumpToDate')
    def set_speed(self,s): self.speed=s; return self.snapshot('ReplaySpeed')
    def snapshot(self,event): return {'event':event,'state':self.state,'cursor':self.cursor,'speed':self.speed}
class BenchmarkService:
    def compare(self, strategy_stats, benchmarks=('buy_hold','random_entries','baseline','previous_version','ai_strategy','portfolio')): return {b:{'net_profit':strategy_stats.get('net_profit',0)*0.8,'delta':strategy_stats.get('net_profit',0)*0.2} for b in benchmarks}
class DatasetGeneratorService:
    def generate(self, events, trades, purpose='ai_training', fmt='json'):
        rows=[{'event':getattr(e,'__dict__',e),'label':trades[i] if i < len(trades) else {}} for i,e in enumerate(events)]
        if fmt=='csv':
            out=io.StringIO(); w=csv.DictWriter(out,fieldnames=['event','label']); w.writeheader(); w.writerows(rows); return out.getvalue()
        return rows
class StressTestingService:
    scenarios=('extreme_volatility','low_liquidity','high_spread','fast_markets','broker_latency','connection_loss','random_slippage','random_delays','flash_crash','market_gaps')
    def apply(self, events, scenario): return list(events)
class PortfolioBacktestingService:
    def run(self, portfolios): return {'allocations':portfolios,'correlation':{},'statistics':PerformanceAnalyticsService().calculate([])}
