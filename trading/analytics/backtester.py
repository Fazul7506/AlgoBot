import numpy as np
from itertools import product
from typing import Any, Dict, List, Optional, Union

from .metrics import (
    win_rate,
    expectancy,
    sharpe_ratio,
    max_drawdown,
    sortino_ratio,
    profit_factor,
    roi,
)

PricePoint = Union[Dict[str, Any], int, float]


class TrendBacktester:
    """Tick-based trend backtest using deterministic next-tick outcomes."""

    def __init__(self, initial_balance: float = 1000.0):
        self.initial_balance = initial_balance

    def run(self):
        from trading.models import Tick
        ticks = list(Tick.objects.order_by('id').values_list('price', flat=True))
        results = []
        wins = losses = 0
        for i in range(5, len(ticks) - 1):
            current, previous, next_tick = ticks[i], ticks[i - 5], ticks[i + 1]
            signal = 'CALL' if current > previous else 'PUT'
            profit = 1 if ((signal == 'CALL' and next_tick > current) or (signal == 'PUT' and next_tick < current)) else -1
            results.append(profit)
            wins += profit > 0
            losses += profit < 0
        ending_balance = self.initial_balance + sum(results)
        return {'wins': wins, 'losses': losses, 'win_rate': win_rate(wins, losses), 'expectancy': expectancy(results), 'sharpe_ratio': sharpe_ratio(results), 'max_drawdown': max_drawdown(results), 'profit_factor': profit_factor(results), 'roi': roi(self.initial_balance, ending_balance)}


class StrategyBacktester:
    """Backtest a strategy without leaking future prices into signal generation."""

    def __init__(self, strategy: Any, prices: List[PricePoint], min_history: int = 20, initial_balance: float = 1000.0):
        self.strategy = strategy
        self.prices = list(prices) if prices is not None else []
        self.min_history = min_history
        self.initial_balance = initial_balance
        self.trades: List[Dict[str, Any]] = []
        self.equity: List[float] = [initial_balance]

    def _extract_price(self, item: PricePoint) -> float:
        if isinstance(item, dict):
            return float(item.get('close', item.get('price', 0.0)))
        return float(item)

    def _extract_timestamp(self, item: PricePoint) -> Optional[Any]:
        return item.get('timestamp') if isinstance(item, dict) else None

    def _normalize_signal(self, signal: Any) -> Optional[str]:
        if isinstance(signal, dict):
            signal = signal.get('signal') or signal.get('direction')
        return str(signal).upper() if signal is not None else None

    def _price_series(self) -> List[float]:
        return [self._extract_price(p) for p in self.prices]

    def _profit_for_signal(self, signal: str, entry_price: float, exit_price: float) -> float:
        if signal == 'BUY':
            return 1.0 if exit_price > entry_price else -1.0
        if signal == 'SELL':
            return 1.0 if exit_price < entry_price else -1.0
        return 0.0

    def run(self) -> Dict[str, Any]:
        price_series = self._price_series()
        if len(price_series) < self.min_history + 1:
            return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'expectancy': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0, 'max_drawdown': 0, 'profit_factor': 0, 'total_profit': 0, 'roi': 0, 'equity_curve': self.equity, 'monthly_returns': {}, 'trade_distribution': {'BUY': 0, 'SELL': 0}, 'trades': []}
        for index in range(self.min_history, len(price_series)):
            history = price_series[:index]
            signal = self._normalize_signal(self.strategy.generate_signal(history))
            if signal not in {'BUY', 'SELL'}:
                continue
            entry_price, exit_price = history[-1], price_series[index]
            profit = self._profit_for_signal(signal, entry_price, exit_price)
            self.trades.append({'index': index, 'signal': signal, 'entry_price': entry_price, 'exit_price': exit_price, 'profit': profit, 'entry_timestamp': self._extract_timestamp(self.prices[index - 1]), 'exit_timestamp': self._extract_timestamp(self.prices[index])})
            self.equity.append(self.equity[-1] + profit)
        results = [t['profit'] for t in self.trades]
        wins = sum(r > 0 for r in results)
        losses = sum(r < 0 for r in results)
        total_profit = float(np.sum(results)) if results else 0.0
        ending_balance = self.initial_balance + total_profit
        return {'total_trades': len(results), 'wins': wins, 'losses': losses, 'win_rate': win_rate(wins, losses), 'expectancy': expectancy(results), 'sharpe_ratio': sharpe_ratio(results), 'sortino_ratio': sortino_ratio(results), 'max_drawdown': max_drawdown(results), 'profit_factor': profit_factor(results), 'total_profit': total_profit, 'roi': roi(self.initial_balance, ending_balance), 'equity_curve': self.equity, 'monthly_returns': self.monthly_returns(), 'trade_distribution': self.trade_distribution(), 'trades': self.trades}

    def equity_curve(self) -> List[float]:
        return list(self.equity)

    def monthly_returns(self) -> Dict[str, float]:
        returns = {}
        for trade in self.trades:
            timestamp = trade.get('exit_timestamp') or trade.get('entry_timestamp')
            if timestamp and hasattr(timestamp, 'strftime'):
                month = timestamp.strftime('%Y-%m')
                returns[month] = returns.get(month, 0.0) + trade['profit']
        return returns

    def trade_distribution(self) -> Dict[str, int]:
        distribution = {'BUY': 0, 'SELL': 0}
        for trade in self.trades:
            if trade['signal'] in distribution:
                distribution[trade['signal']] += 1
        return distribution

    def replay_candles(self) -> Dict[str, Any]:
        return self.run()

    def replay_ticks(self) -> Dict[str, Any]:
        return self.run()


class StrategyOptimizer:
    """Grid-search optimizer with out-of-sample walk-forward validation."""

    def __init__(self, strategy_cls: Any, prices: List[PricePoint], param_grid: Optional[Dict[str, List[Any]]] = None, min_history: int = 20):
        self.strategy_cls = strategy_cls
        self.prices = list(prices) if prices is not None else []
        self.param_grid = param_grid or {}
        self.min_history = min_history

    def _evaluate(self, params: Dict[str, Any], prices: Optional[List[PricePoint]] = None) -> Dict[str, Any]:
        result = StrategyBacktester(self.strategy_cls(**params), prices if prices is not None else self.prices, min_history=self.min_history).run()
        result['params'] = params
        result['metrics'] = {k: result.get(k, 0) for k in ('win_rate', 'profit_factor', 'sharpe_ratio', 'sortino_ratio', 'max_drawdown', 'roi', 'total_trades')}
        result['score'] = (result['metrics']['win_rate'] / 100) * 0.25 + min(result['metrics']['profit_factor'], 5) / 5 * 0.25 + max(min(result['metrics']['sharpe_ratio'], 5), -5) / 5 * 0.20 + max(min(result['metrics']['sortino_ratio'], 5), -5) / 5 * 0.15 + max(min(result['metrics']['roi'], 100), -100) / 100 * 0.15
        return result

    def grid_search(self, top_n: int = 3) -> List[Dict[str, Any]]:
        if not self.param_grid:
            return []
        keys, values = list(self.param_grid), list(self.param_grid.values())
        candidates = [self._evaluate(dict(zip(keys, combination))) for combination in product(*values)]
        candidates.sort(key=lambda item: item['score'], reverse=True)
        return candidates[:max(1, top_n)]

    def walk_forward_test(self, train_size: int, test_size: int, step_size: int = 1) -> Dict[str, Any]:
        if train_size <= self.min_history or test_size < 1 or step_size < 1 or len(self.prices) < train_size + test_size or not self.param_grid:
            return {'folds': [], 'validated': False, 'reason': 'Insufficient history or invalid walk-forward configuration'}
        keys, values = list(self.param_grid), list(self.param_grid.values())
        folds = []
        for start in range(0, len(self.prices) - train_size - test_size + 1, step_size):
            train = self.prices[start:start + train_size]
            test = self.prices[start + train_size:start + train_size + test_size]
            evaluations = [self._evaluate(dict(zip(keys, combo)), train) for combo in product(*values)]
            if not evaluations:
                continue
            best = max(evaluations, key=lambda item: item['score'])
            # Critical: evaluate the selected parameters on TEST ONLY. No train+test leakage.
            out = self._evaluate(best['params'], test)
            folds.append({'fold': len(folds) + 1, 'train_range': (start, start + train_size - 1), 'test_range': (start + train_size, start + train_size + test_size - 1), 'best_params': best['params'], 'train_score': best['score'], 'test_metrics': out['metrics'], 'test_score': out['score']})
        test_scores = [f['test_score'] for f in folds]
        return {'folds': folds, 'validated': bool(folds), 'average_test_score': float(np.mean(test_scores)) if test_scores else 0.0, 'average_win_rate': float(np.mean([f['test_metrics']['win_rate'] for f in folds])) if folds else 0.0, 'average_profit_factor': float(np.mean([f['test_metrics']['profit_factor'] for f in folds])) if folds else 0.0, 'average_sharpe_ratio': float(np.mean([f['test_metrics']['sharpe_ratio'] for f in folds])) if folds else 0.0, 'average_sortino_ratio': float(np.mean([f['test_metrics']['sortino_ratio'] for f in folds])) if folds else 0.0}
