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
        self.balance = float(balance)
        self.risk_pct = float(risk_pct)
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        # Retained as a profile/calculator reference. It is NOT an execution ceiling.
        self.max_stake_pct = float(max_stake_pct)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.min_stake = float(min_stake)
        self.start_balance = self.balance
        self.daily_loss = 0.0
        self.consecutive_losses = 0
        self.peak_balance = self.balance
        self.max_drawdown = 0.0

    def calculate_stake(self) -> float:
        """Return the profile's suggested stake, never the user's maximum allowed stake."""
        return round(min(max(self.balance * self.risk_pct, self.min_stake), max(self.balance, 0.0)), 2)

    def calculate_risk(self, stake: float, *, projected_loss: Optional[float] = None) -> dict:
        """Return an advisory risk assessment for a proposed stake.

        This method deliberately does not reject the stake. Execution may still be
        stopped by account/broker authority, an emergency kill switch, or an invalid
        order. Profile thresholds are warnings, not stake ceilings.
        """
        stake = max(float(stake or 0.0), 0.0)
        balance = max(self.balance, 0.0)
        suggested = self.calculate_stake()
        pct = (stake / balance) if balance else 1.0
        projected = stake if projected_loss is None else max(float(projected_loss), 0.0)
        daily_remaining = self.get_remaining_daily_risk()
        warnings = []
        if balance and stake > balance:
            warnings.append('Stake exceeds available account balance and the broker may reject the order.')
        if balance and pct > self.max_stake_pct:
            warnings.append(f'Stake is above the configured advisory level of {self.max_stake_pct * 100:.1f}% of balance.')
        if suggested and stake > suggested:
            warnings.append(f'Stake is above the profile suggestion of {suggested:.2f}.')
        if projected > daily_remaining:
            warnings.append(f'Projected loss exceeds the remaining daily-risk reference of {daily_remaining:.2f}.')
        if self.consecutive_losses >= self.max_consecutive_losses:
            warnings.append(f'{self.consecutive_losses} consecutive losses have been recorded.')
        if self.get_drawdown_pct() >= self.max_drawdown_pct:
            warnings.append(f'Current drawdown is at or above the configured {self.max_drawdown_pct * 100:.1f}% reference.')
        return {
            'stake': round(stake, 2),
            'balance': round(balance, 2),
            'stake_pct': round(pct, 6),
            'suggested_stake': suggested,
            'advisory_limit': round(balance * self.max_stake_pct, 2),
            'remaining_daily_risk': daily_remaining,
            'projected_loss': round(projected, 2),
            'warnings': warnings,
            'warning': bool(warnings),
            'execution_allowed_by_stake_policy': True,
        }

    def can_trade(self) -> bool:
        # Only account viability is a hard requirement here. Risk profile thresholds
        # are advisory; emergency-stop/broker/account authority remain separate gates.
        return self.balance > 0

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
        balance = float(account_balance if account_balance is not None else self.balance)
        return round(min(max(balance * self.risk_pct, self.min_stake), max(balance, 0.0)), 2)

    def get_drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return round((self.peak_balance - self.balance) / self.peak_balance, 4)

    def get_remaining_daily_risk(self) -> float:
        limit = self.start_balance * self.max_daily_loss_pct
        return round(max(limit - self.daily_loss, 0.0), 2)
