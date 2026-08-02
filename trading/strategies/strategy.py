import numpy as np
import time
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

        # Trend alignment filter
        if short > mid > long:
            return "CALL"

        if short < mid < long:
            return "PUT"

        return None

class RiskManager:

    def __init__(self, balance, risk=0.01, max_daily_loss=0.05):
        self.balance = balance
        self.risk = risk
        self.max_daily_loss = max_daily_loss

        self.start_balance = balance

    def calculate_stake(self):
        stake = self.balance * self.risk
        return max(round(stake, 2), 0.35)

    def can_trade(self):
        loss_limit = self.start_balance * self.max_daily_loss
        return (self.start_balance - self.balance) < loss_limit

    def update_balance(self, pnl):
        self.balance += pnl

class Portfolio:

    def __init__(self):
        self.trades = []
        self.equity_curve = []

    def record_trade(self, direction, stake, pnl):
        self.trades.append({
            "direction": direction,
            "stake": stake,
            "pnl": pnl,
            "time": time.time()
        })

    def update_equity(self, balance):
        self.equity_curve.append(balance)

    def win_rate(self):
        if not self.trades:
            return 0

        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return wins / len(self.trades)

    def total_pnl(self):
        return sum(t["pnl"] for t in self.trades)
    
class ExecutionEngine:

    def __init__(self):
        self.last_trade_time = 0
        self.cooldown = 5  # seconds

    def can_execute(self):
        return time.time() - self.last_trade_time > self.cooldown

    def execute(self, signal, stake):
        self.last_trade_time = time.time()

        # MOCK execution (replace with Deriv API later)
        print(f"[EXECUTING] {signal} | stake={stake}")

        # Simulated result (replace with real payout)
        outcome = np.random.choice([1, -1], p=[0.55, 0.45])
        pnl = stake * outcome

        return pnl
    
class Backtester:

    def __init__(self, prices, strategy):
        self.prices = prices
        self.strategy = strategy
        self.returns = []

    def run(self):

        for i in range(20, len(self.prices)):
            window = self.prices[:i]

            signal = self.strategy.signal(window)

            if signal == "CALL" and self.prices[i] > self.prices[i-1]:
                self.returns.append(1)

            elif signal == "PUT" and self.prices[i] < self.prices[i-1]:
                self.returns.append(1)

            elif signal:
                self.returns.append(-1)

    def sharpe(self):
        arr = np.array(self.returns)
        return arr.mean() / (arr.std() + 1e-9)

    def win_rate(self):
        arr = np.array(self.returns)
        return (arr > 0).mean()
    
def send_telegram(msg, token, chat_id):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        requests.get(url, params={
            "chat_id": chat_id,
            "text": msg
        })
    except Exception as e:
        print("Telegram error:", e)

class TradingEngine:

    def __init__(self, strategy, risk, portfolio, executor):
        self.strategy = strategy
        self.risk = risk
        self.portfolio = portfolio
        self.executor = executor

        self.prices = []

    def on_tick(self, price):

        self.prices.append(price)

        if len(self.prices) < 20:
            return

        # risk gate
        if not self.risk.can_trade():
            print("Daily loss limit reached.")
            return

        # cooldown gate
        if not self.executor.can_execute():
            return

        signal = self.strategy.signal(self.prices)

        if not signal:
            return

        stake = self.risk.calculate_stake()
        pnl = self.executor.execute(signal, stake)

        self.risk.update_balance(pnl)
        self.portfolio.record_trade(signal, stake, pnl)
        self.portfolio.update_equity(self.risk.balance)

        print(f"{signal} | PnL={pnl} | Balance={self.risk.balance}")