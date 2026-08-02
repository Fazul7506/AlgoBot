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
    """Simplified tick-based trend backtest implementation."""

    def __init__(self, initial_balance: float = 1000.0):
        self.initial_balance = initial_balance

    def run(self):
        from trading.models import Tick

        ticks = list(
            Tick.objects.order_by('id')
            .values_list('price', flat=True)
        )

        results = []
        wins = 0
        losses = 0

        for i in range(5, len(ticks) - 1):
            current = ticks[i]
            previous = ticks[i - 5]
            signal = 'CALL' if current > previous else 'PUT'
            next_tick = ticks[i + 1]

            if signal == 'CALL':
                profit = 1 if next_tick > current else -1
            else:
                profit = 1 if next_tick < current else -1

            results.append(profit)
            if profit > 0:
                wins += 1
            else:
                losses += 1

        total_profit = sum(results)
        ending_balance = self.initial_balance + total_profit
        return {
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate(wins, losses),
            'expectancy': expectancy(results),
            'sharpe_ratio': sharpe_ratio(results),
            'max_drawdown': max_drawdown(results),
            'profit_factor': self._profit_factor(results),
            'roi': roi(self.initial_balance, ending_balance),
        }

    def _profit_factor(self, results: List[float]) -> float:
        wins = sum(r for r in results if r > 0)
        losses = -sum(r for r in results if r < 0)
        return round((wins / losses) if losses > 0 else float(wins), 4)


class StrategyBacktester:
    """Backtester for strategy evaluation on candle or tick history."""

    def __init__(self, strategy: Any, prices: List[PricePoint], min_history: int = 20, initial_balance: float = 1000.0):
        self.strategy = strategy
        self.prices = list(prices) if prices is not None else []
        self.min_history = min_history
        self.initial_balance = initial_balance
        self.trades: List[Dict[str, Any]] = []
        self.equity: List[float] = [initial_balance]

    def _extract_price(self, candle_or_price: PricePoint) -> float:
        if isinstance(candle_or_price, dict):
            return float(candle_or_price.get('close', candle_or_price.get('price', 0.0)))
        return float(candle_or_price)

    def _extract_timestamp(self, candle_or_price: PricePoint) -> Optional[Any]:
        if isinstance(candle_or_price, dict):
            return candle_or_price.get('timestamp')
        return None

    def _normalize_signal(self, signal: Any) -> Optional[str]:
        if isinstance(signal, dict):
            return signal.get('signal') or signal.get('direction')
        if isinstance(signal, str):
            return signal
        return None

    def _price_series(self) -> List[float]:
        return [self._extract_price(p) for p in self.prices]

    def _profit_for_signal(self, signal: str, entry_price: float, exit_price: float) -> float:
        if signal == 'BUY':
            return 1.0 if exit_price > entry_price else -1.0
        if signal == 'SELL':
            return 1.0 if exit_price < entry_price else -1.0
        return 0.0

    def _profit_factor(self, results: List[float]) -> float:
        wins = sum(r for r in results if r > 0)
        losses = -sum(r for r in results if r < 0)
        if losses <= 0:
            return round(float(wins), 4)
        return round(wins / losses, 4)

    def run(self) -> Dict[str, Any]:
        price_series = self._price_series()

        if len(price_series) < self.min_history + 1:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'expectancy': 0,
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'total_profit': 0,
                'equity_curve': self.equity,
                'monthly_returns': {},
                'trade_distribution': {'BUY': 0, 'SELL': 0},
                'trades': [],
            }

        for index in range(self.min_history, len(price_series)):
            history = price_series[:index]
            signal = self.strategy.generate_signal(history)
            normalized_signal = self._normalize_signal(signal)
            if normalized_signal not in ['BUY', 'SELL']:
                continue

            entry_price = history[-1]
            exit_price = price_series[index]
            profit = self._profit_for_signal(normalized_signal, entry_price, exit_price)
            self.trades.append({
                'index': index,
                'signal': normalized_signal,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'profit': profit,
                'entry_timestamp': self._extract_timestamp(self.prices[index - 1]) if index > 0 else None,
                'exit_timestamp': self._extract_timestamp(self.prices[index]),
            })
            self.equity.append(self.equity[-1] + profit)

        results = [trade['profit'] for trade in self.trades]
        wins = sum(1 for r in results if r > 0)
        losses = sum(1 for r in results if r <= 0)
        total_profit = float(np.sum(results)) if results else 0
        ending_balance = self.initial_balance + total_profit

        return {
            'total_trades': len(results),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate(wins, losses),
            'expectancy': expectancy(results),
            'sharpe_ratio': sharpe_ratio(results),
            'sortino_ratio': sortino_ratio(results),
            'max_drawdown': max_drawdown(results),
            'profit_factor': self._profit_factor(results),
            'total_profit': total_profit,
            'roi': roi(self.initial_balance, ending_balance),
            'equity_curve': self.equity,
            'monthly_returns': self.monthly_returns(),
            'trade_distribution': self.trade_distribution(),
            'trades': self.trades,
        }

    def equity_curve(self) -> List[float]:
        return list(self.equity)

    def monthly_returns(self) -> Dict[str, float]:
        returns = {}
        for trade in self.trades:
            timestamp = trade.get('exit_timestamp') or trade.get('entry_timestamp')
            if not timestamp:
                continue
            month = timestamp.strftime('%Y-%m')
            returns.setdefault(month, 0.0)
            returns[month] += trade['profit']
        return returns

    def trade_distribution(self) -> Dict[str, int]:
        distribution = {'BUY': 0, 'SELL': 0}
        for trade in self.trades:
            direction = trade.get('signal')
            if direction in distribution:
                distribution[direction] += 1
        return distribution

    def replay_candles(self) -> Dict[str, Any]:
        """Alias for a candle-based backtest run."""
        return self.run()

    def replay_ticks(self) -> Dict[str, Any]:
        """Alias for a tick-based backtest run."""
        return self.run()


class StrategyOptimizer:
    """Optimize strategy hyperparameters and run walk-forward evaluation."""

    def __init__(self, strategy_cls: Any, prices: List[PricePoint], param_grid: Optional[Dict[str, List[Any]]] = None, min_history: int = 20):
        self.strategy_cls = strategy_cls
        self.prices = list(prices) if prices is not None else []
        self.param_grid = param_grid or {}
        self.min_history = min_history

    def _evaluate(self, params: Dict[str, Any], prices: Optional[List[PricePoint]] = None) -> Dict[str, Any]:
        strategy = self.strategy_cls(**params)
        backtester = StrategyBacktester(strategy, prices if prices is not None else self.prices, min_history=self.min_history)
        result = backtester.run()
        result['params'] = params
        result['metrics'] = {
            'win_rate': result.get('win_rate', 0),
            'profit_factor': result.get('profit_factor', 0),
            'sharpe_ratio': result.get('sharpe_ratio', 0),
            'sortino_ratio': result.get('sortino_ratio', 0),
            'max_drawdown': result.get('max_drawdown', 0),
        }
        result['score'] = result['metrics']['win_rate'] * 0.4 + result['metrics']['profit_factor'] * 0.4 + (result['metrics']['sharpe_ratio'] * 0.2)
        return result

    def grid_search(self, top_n: int = 3) -> List[Dict[str, Any]]:
        if not self.param_grid:
            return []

        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        candidates: List[Dict[str, Any]] = []

        for combination in product(*values):
            params = dict(zip(keys, combination))
            candidates.append(self._evaluate(params))

        candidates.sort(key=lambda item: item['score'], reverse=True)
        return candidates[:top_n]

    def walk_forward_test(self, train_size: int, test_size: int, step_size: int = 1) -> Dict[str, Any]:
        if not self.param_grid or len(self.prices) < train_size + test_size:
            return {'folds': []}

        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        folds: List[Dict[str, Any]] = []

        for start in range(0, len(self.prices) - train_size - test_size + 1, step_size):
            train_prices = self.prices[start:start + train_size]
            test_prices = self.prices[start + train_size:start + train_size + test_size]

            best_score = float('-inf')
            best_params = None
            for combination in product(*values):
                params = dict(zip(keys, combination))
                evaluation = self._evaluate(params, prices=train_prices)
                if evaluation['score'] > best_score:
                    best_score = evaluation['score']
                    best_params = params

            if best_params is None:
                continue

            test_result = self._evaluate(best_params, prices=train_prices + test_prices)
            folds.append({
                'fold': len(folds) + 1,
                'train_range': (start, start + train_size - 1),
                'test_range': (start + train_size, start + train_size + test_size - 1),
                'best_params': best_params,
                'train_score': best_score,
                'test_metrics': test_result,
            })

        average_win_rate = np.mean([f['test_metrics']['win_rate'] for f in folds]) if folds else 0.0
        average_profit_factor = np.mean([f['test_metrics']['profit_factor'] for f in folds]) if folds else 0.0
        average_sharpe_ratio = np.mean([f['test_metrics']['sharpe_ratio'] for f in folds]) if folds else 0.0

        return {
            'folds': folds,
            'average_win_rate': average_win_rate,
            'average_profit_factor': average_profit_factor,
            'average_sharpe_ratio': average_sharpe_ratio,
        }
