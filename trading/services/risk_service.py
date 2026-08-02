from typing import Optional


class RiskService:

    def __init__(
        self,
        balance: float = 1000.0,
        risk_pct: float = 0.01,
        max_daily_loss_pct: float = 0.05,
        max_stake_pct: float = 0.10,
        max_consecutive_losses: int = 3,
        max_drawdown_pct: float = 0.15,
        min_stake: float = 0.35,
    ):
        self.balance = balance
        self.risk_pct = risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_stake_pct = max_stake_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_drawdown_pct = max_drawdown_pct
        self.min_stake = min_stake

        self.start_balance = balance
        self.daily_loss = 0.0
        self.consecutive_losses = 0
        self.peak_balance = balance
        self.max_drawdown = 0.0

    def calculate_stake(self) -> float:
        stake = self.balance * self.risk_pct
        stake = min(stake, self.balance * self.max_stake_pct)
        stake = max(stake, self.min_stake)
        return round(min(stake, self.balance), 2)

    def can_trade(self) -> bool:
        if self.balance <= 0:
            return False

        if self.daily_loss >= (self.start_balance * self.max_daily_loss_pct):
            return False

        if self.consecutive_losses >= self.max_consecutive_losses:
            return False

        if self.balance <= self.peak_balance * (1 - self.max_drawdown_pct):
            return False

        return True

    def reset_daily_loss(self) -> None:
        self.daily_loss = 0.0

    def record_pnl(self, pnl: float) -> None:
        self.balance += pnl

        if pnl < 0:
            self.daily_loss += abs(pnl)
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self.peak_balance = max(self.peak_balance, self.balance)
        drawdown = self.peak_balance - self.balance
        self.max_drawdown = max(self.max_drawdown, drawdown)

    def get_balance(self) -> float:
        return self.balance

    def get_position_size(self, account_balance: Optional[float] = None) -> float:
        balance = account_balance if account_balance is not None else self.balance
        stake = balance * self.risk_pct
        stake = min(stake, balance * self.max_stake_pct)
        stake = max(stake, self.min_stake)
        return round(min(stake, balance), 2)

    def get_drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return round((self.peak_balance - self.balance) / self.peak_balance, 4)

    def get_remaining_daily_risk(self) -> float:
        limit = self.start_balance * self.max_daily_loss_pct
        return round(max(limit - self.daily_loss, 0.0), 2)
