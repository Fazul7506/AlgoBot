from django.utils import timezone
from trading.models import Trade, Strategy
from trading.services.notification_service import NotificationService
from trading.services.copy_service import CopyService


class TradeService:

    CONTRACT_MAP = {
        'BUY': 'CALL',
        'SELL': 'PUT',
    }

    def __init__(self, risk_service=None, user=None):
        self.risk_service = risk_service
        self.user = user

    def _resolve_strategy_fk(self, strategy_name):
        if not strategy_name:
            return None

        return Strategy.objects.filter(name__iexact=strategy_name).first()

    def open_trade(
        self,
        symbol,
        signal_direction,
        entry_price,
        strategy_name,
        confidence=50,
        market_regime=None,
        is_paper=True,
        user=None,
    ):
        if self.risk_service and not self.risk_service.can_trade():
            return None

        stake = self.risk_service.get_position_size() if self.risk_service else 0.35

        if self.risk_service:
            remaining_risk = self.risk_service.get_remaining_daily_risk()
            stake = min(stake, remaining_risk)

            if stake < self.risk_service.min_stake:
                return None

        resolved_user = user or getattr(self, 'user', None)
        if self.risk_service and not resolved_user:
            resolved_user = getattr(self.risk_service, 'user', None)

        contract_type = self.CONTRACT_MAP.get(signal_direction, signal_direction)

        # If user has a subscription, enforce max concurrent trades
        if user:
            try:
                sub = getattr(user, 'subscription', None)
                if sub and sub.max_concurrent_trades is not None:
                    open_trades = Trade.objects.filter(user=user, status='OPEN').count()
                    if open_trades >= sub.max_concurrent_trades:
                        return None
            except Exception:
                pass

        trade = Trade.objects.create(
            user=resolved_user,
            strategy_fk=self._resolve_strategy_fk(strategy_name),
            strategy=strategy_name,
            symbol=symbol,
            contract_type=contract_type,
            entry_price=entry_price,
            stake=stake,
            profit=0.0,
            profit_pct=0.0,
            status='OPEN',
            strategy_confidence=confidence,
            entry_reason=f"Signal {signal_direction} from {strategy_name} ({market_regime})",
            indicators_snapshot={'market_regime': market_regime},
            is_paper=is_paper,
        )

        if getattr(trade, 'user', None):
            NotificationService(user=trade.user).notify_trade_opened(trade)
            # Trigger copy trading replication for followers
            try:
                CopyService().handle_leader_trade(trade)
            except Exception:
                # Non-fatal: log and continue
                import logging
                logging.exception('CopyService failed while handling leader trade')

        return trade

    def close_trade(
        self,
        trade: Trade,
        pnl: float,
        exit_price: float = None,
        exit_reason: str = None,
    ):
        trade.status = 'CLOSED'
        if exit_price is not None:
            trade.exit_price = exit_price
        trade.closed_at = timezone.now()
        trade.profit = pnl
        trade.profit_pct = round((pnl / trade.stake) * 100, 2) if trade.stake else 0.0
        if exit_reason:
            trade.exit_reason = exit_reason
        trade.save()

        if self.risk_service:
            self.risk_service.record_pnl(pnl)

        if getattr(trade, 'user', None):
            if exit_reason == 'target' or (pnl is not None and pnl > 0):
                NotificationService(user=trade.user).notify_profit_target(trade)
            elif exit_reason in ('drawdown', 'stop_loss', 'loss') or (pnl is not None and pnl < 0):
                NotificationService(user=trade.user).notify_drawdown_warning(trade)
            NotificationService(user=trade.user).notify_trade_closed(trade)

        return trade
