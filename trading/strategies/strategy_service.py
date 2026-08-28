from typing import List, Optional, Dict, Any
from datetime import datetime
from trading.models import Tick
from trading.models.core import BacktestResult, Strategy as StrategyModel, Candle
from trading.strategies import registry
from trading.analytics.backtester import StrategyBacktester, StrategyOptimizer


class StrategyService:
    @staticmethod
    def list_available() -> List[str]:
        return registry.available()

    @staticmethod
    def build_instance(strategy_record: StrategyModel):
        cls = registry.get(strategy_record.name)
        if not cls:
            cls = registry.get('momentum')
        try:
            return cls(**(strategy_record.config or {}))
        except Exception:
            return cls()

    @staticmethod
    def _historic_prices(symbol: str, timeframe: str = 'M1', data_type: str = 'auto', start_date=None, end_date=None):
        """Return broker-ingested historical data restricted to the requested interval."""
        if data_type in ('auto', 'candles'):
            qs = Candle.objects.filter(symbol=symbol, timeframe=timeframe).order_by('timestamp')
            if start_date is not None:
                qs = qs.filter(timestamp__gte=start_date)
            if end_date is not None:
                qs = qs.filter(timestamp__lte=end_date)
            candles = list(qs.values('open', 'high', 'low', 'close', 'timestamp'))
            if candles or data_type == 'candles':
                return candles

        if data_type in ('auto', 'ticks'):
            qs = Tick.objects.filter(symbol=symbol).order_by('epoch')
            if start_date is not None:
                qs = qs.filter(received_at__gte=start_date)
            if end_date is not None:
                qs = qs.filter(received_at__lte=end_date)
            return list(qs.values_list('price', flat=True))
        return []

    @staticmethod
    def run_backtest(strategy_record: StrategyModel, symbol: str, timeframe: str = 'M1', data_type: str = 'auto', min_history: int = 20, start_date=None, end_date=None):
        if start_date is not None and end_date is not None and end_date <= start_date:
            raise ValueError('end_date must be later than start_date')
        prices = StrategyService._historic_prices(symbol, timeframe=timeframe, data_type=data_type, start_date=start_date, end_date=end_date)
        if not prices:
            raise ValueError('No broker historical data exists for the selected symbol, timeframe and date range')
        strategy_instance = StrategyService.build_instance(strategy_record)
        result = StrategyBacktester(strategy_instance, prices, min_history=min_history).run()

        BacktestResult.objects.create(
            strategy_fk=strategy_record, strategy=strategy_record.name, symbol=symbol, timeframe=timeframe,
            start_date=start_date, end_date=end_date, initial_balance=1000,
            total_trades=result['total_trades'], wins=result['wins'], losses=result['losses'],
            win_rate=result['win_rate'], expectancy=result['expectancy'], sharpe_ratio=result['sharpe_ratio'],
            sortino_ratio=result.get('sortino_ratio', 0), max_drawdown=result['max_drawdown'], max_drawdown_pct=0,
            profit_factor=result.get('profit_factor', 0), total_profit=result.get('total_profit', 0),
            total_profit_pct=0, final_balance=1000 + result.get('total_profit', 0), trades_log=result.get('trades', []),
        )
        return result

    @staticmethod
    def compare_strategies(strategy_names: Optional[List[str]] = None, symbol: str = 'R_75', timeframe: str = 'M1'):
        if not strategy_names:
            strategy_names = StrategyService.list_available()
        comparison = []
        for name in strategy_names:
            strategy_record = StrategyModel.objects.filter(name=name).first()
            if not strategy_record:
                comparison.append({'strategy': name, 'error': 'Strategy not found'}); continue
            comparison.append({'strategy': name, 'result': StrategyService.run_backtest(strategy_record, symbol=symbol, timeframe=timeframe)})
        return comparison

    @staticmethod
    def optimize_strategy(strategy_record: StrategyModel, symbol: str = 'R_75', timeframe: str = 'M1', param_grid=None, walk_forward: Optional[Dict[str, Any]] = None, top_n: int = 3, min_history: int = 20, data_type: str = 'auto', start_date=None, end_date=None):
        prices = StrategyService._historic_prices(symbol, timeframe=timeframe, data_type=data_type, start_date=start_date, end_date=end_date)
        strategy_cls = registry.get(strategy_record.name)
        if not strategy_cls:
            return {'error': 'Strategy class not found'}
        optimizer = StrategyOptimizer(strategy_cls, prices, param_grid=param_grid or {}, min_history=min_history)
        if walk_forward:
            return optimizer.walk_forward_test(train_size=int(walk_forward.get('train_size', 50)), test_size=int(walk_forward.get('test_size', 20)), step_size=int(walk_forward.get('step_size', 5)))
        return optimizer.grid_search(top_n=top_n)
