import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import requests


class BaseStrategy:
    def signal(self, prices):
        raise NotImplementedError


class TrendStrategy(BaseStrategy):
    def signal(self, prices):
        if len(prices) < 20:
            return None
        short = np.mean(prices[-3:])
        mid = np.mean(prices[-10:])
        long = np.mean(prices[-20:])
        if short > mid > long:
            return "CALL"
        if short < mid < long:
            return "PUT"
        return None


class RiskManager:
    def __init__(self, balance, risk=0.01, max_daily_loss=0.05):
        self.balance = float(balance)
        self.risk = float(risk)
        self.max_daily_loss = float(max_daily_loss)
        self.start_balance = self.balance

    def calculate_stake(self):
        return max(round(self.balance * self.risk, 2), 0.35)

    def can_trade(self):
        loss_limit = self.start_balance * self.max_daily_loss
        return (self.start_balance - self.balance) < loss_limit

    def update_balance(self, pnl):
        self.balance += float(pnl)


class Portfolio:
    def __init__(self):
        self.trades = []
        self.equity_curve = []

    def record_trade(self, direction, stake, pnl):
        self.trades.append({"direction": direction, "stake": stake, "pnl": pnl, "time": time.time()})

    def update_equity(self, balance):
        self.equity_curve.append(balance)

    def win_rate(self):
        return sum(t["pnl"] > 0 for t in self.trades) / len(self.trades) if self.trades else 0

    def total_pnl(self):
        return sum(t["pnl"] for t in self.trades)


@dataclass
class ExecutionResult:
    status: str
    pnl: Optional[float] = None
    broker_order_id: Optional[str] = None
    raw: Optional[dict] = None


class ExecutionEngine:
    """Broker-backed execution coordinator; never fabricates a fill or PnL."""
    def __init__(self, executor: Optional[Callable] = None, cooldown: float = 5):
        self.executor = executor
        self.last_trade_time = 0.0
        self.cooldown = cooldown

    def can_execute(self):
        return self.executor is not None and (time.time() - self.last_trade_time) >= self.cooldown

    def execute(self, signal, stake, **context):
        if self.executor is None:
            raise RuntimeError("No broker execution adapter configured; refusing simulated execution")
        if not self.can_execute():
            raise RuntimeError("Execution is on cooldown or broker executor is unavailable")
        self.last_trade_time = time.time()
        result = self.executor(signal=signal, stake=stake, **context)
        if isinstance(result, ExecutionResult):
            return result
        if isinstance(result, dict):
            return ExecutionResult(status=result.get("status", "submitted"), pnl=result.get("pnl"), broker_order_id=result.get("broker_order_id"), raw=result)
        return ExecutionResult(status="submitted", raw={"result": result})


class Backtester:
    def __init__(self, prices, strategy):
        self.prices = prices
        self.strategy = strategy
        self.returns = []

    def run(self):
        for i in range(20, len(self.prices)):
            window = self.prices[:i]
            signal = self.strategy.signal(window)
            if signal == "CALL" and self.prices[i] > self.prices[i - 1]:
                self.returns.append(1)
            elif signal == "PUT" and self.prices[i] < self.prices[i - 1]:
                self.returns.append(1)
            elif signal:
                self.returns.append(-1)
        return self.returns

    def sharpe(self):
        arr = np.array(self.returns, dtype=float)
        return float(arr.mean() / (arr.std() + 1e-9)) if len(arr) else 0.0

    def win_rate(self):
        arr = np.array(self.returns, dtype=float)
        return float((arr > 0).mean()) if len(arr) else 0.0


def send_telegram(msg, token, chat_id):
    if not token or not chat_id:
        return False
    try:
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", params={"chat_id": chat_id, "text": msg}, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


class TradingEngine:
    def __init__(self, strategy, risk, portfolio, executor):
        self.strategy = strategy
        self.risk = risk
        self.portfolio = portfolio
        self.executor = executor
        self.prices = []

    def on_tick(self, price, **context):
        self.prices.append(float(price))
        if len(self.prices) < 20 or not self.risk.can_trade() or not self.executor.can_execute():
            return None
        signal = self.strategy.signal(self.prices)
        if not signal:
            return None
        stake = self.risk.calculate_stake()
        result = self.executor.execute(signal, stake, **context)
        if result.pnl is not None:
            self.risk.update_balance(result.pnl)
            self.portfolio.record_trade(signal, stake, result.pnl)
            self.portfolio.update_equity(self.risk.balance)
        return result
