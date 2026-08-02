"""
Paper Trading Execution Service
Handles simulated trades, real-time market simulation, and paper account management.
"""

from django.utils import timezone
from django.db.models import Q, F, Sum, Avg
from datetime import datetime, timedelta
from trading.models.core import Trade, Strategy, PerformanceSnapshot
from trading.services.trade_service import TradeService
from trading.services.risk_service import RiskService


class PaperTradingService:
    """Manages simulated paper trading execution and account state."""

    def __init__(self, initial_balance=10000.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.equity = initial_balance
        self.trade_service = TradeService()
        self.risk_service = RiskService()

    def execute_paper_trade(self, symbol, direction, entry_price, strategy_name, 
                            confidence=50, market_regime=None):
        """
        Execute a simulated trade in paper account.
        
        Args:
            symbol: Trading symbol
            direction: BUY or SELL
            entry_price: Entry price
            strategy_name: Strategy name
            confidence: Signal confidence 0-100
            market_regime: Market condition (bull/bear/neutral)
            
        Returns:
            Trade object or None if execution failed
        """
        trade = self.trade_service.open_trade(
            symbol=symbol,
            signal_direction=direction,
            entry_price=entry_price,
            strategy_name=strategy_name,
            confidence=confidence,
            market_regime=market_regime,
            is_paper=True,
        )
        if trade:
            self.current_balance -= trade.stake
        return trade

    def close_paper_trade(self, trade, exit_price, exit_reason=None):
        """
        Close a paper trade with simulated exit.
        
        Args:
            trade: Trade object to close
            exit_price: Exit price
            exit_reason: Reason for exit
            
        Returns:
            Updated trade object
        """
        if trade.contract_type == 'CALL':
            pnl = (exit_price - trade.entry_price) * (trade.stake / trade.entry_price)
        else:
            pnl = (trade.entry_price - exit_price) * (trade.stake / trade.entry_price)
        
        closed_trade = self.trade_service.close_trade(
            trade, pnl=pnl, exit_price=exit_price, exit_reason=exit_reason or 'simulated'
        )
        
        # Update balance
        self.current_balance += trade.stake + pnl
        self.equity = self.current_balance
        
        return closed_trade

    def simulate_market_move(self, symbol, current_price, new_price, open_trades=None):
        """
        Simulate market price movement and update open trades.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            new_price: New price
            open_trades: Optional list of trades to simulate
            
        Returns:
            List of affected trades with updated PnL
        """
        if open_trades is None:
            open_trades = Trade.objects.filter(
                symbol=symbol, 
                status='OPEN', 
                is_paper=True
            )
        
        affected_trades = []
        for trade in open_trades:
            if trade.contract_type == 'CALL':
                unrealized_pnl = (new_price - trade.entry_price) * (trade.stake / trade.entry_price)
            else:
                unrealized_pnl = (trade.entry_price - new_price) * (trade.stake / trade.entry_price)
            
            affected_trades.append({
                'trade_id': trade.id,
                'symbol': symbol,
                'direction': 'BUY' if trade.contract_type == 'CALL' else 'SELL',
                'entry_price': trade.entry_price,
                'current_price': new_price,
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_pct': round((unrealized_pnl / trade.stake) * 100, 2) if trade.stake else 0,
            })
        
        return affected_trades

    def get_account_state(self):
        """Get current paper account state."""
        open_trades = Trade.objects.filter(status='OPEN', is_paper=True)
        closed_trades = Trade.objects.filter(status='CLOSED', is_paper=True)
        
        total_trades = open_trades.count() + closed_trades.count()
        winning_trades = closed_trades.filter(profit__gt=0).count()
        losing_trades = closed_trades.filter(profit__lt=0).count()
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = closed_trades.aggregate(Sum('profit'))['profit__sum'] or 0
        
        return {
            'balance': self.current_balance,
            'equity': self.equity,
            'initial_balance': self.initial_balance,
            'total_pnl': total_pnl,
            'total_pnl_pct': round((total_pnl / self.initial_balance) * 100, 2),
            'open_trades': open_trades.count(),
            'closed_trades': closed_trades.count(),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(win_rate, 2),
        }

    def log_performance_snapshot(self):
        """Create a performance snapshot for current account state."""
        state = self.get_account_state()
        drawdown = max(0, self.initial_balance - self.current_balance)
        drawdown_pct = (drawdown / self.initial_balance) * 100 if self.initial_balance > 0 else 0
        
        snapshot = PerformanceSnapshot.objects.create(
            balance=state['balance'],
            equity=state['equity'],
            drawdown=drawdown,
            drawdown_pct=drawdown_pct,
            pnl=state['total_pnl'],
            pnl_pct=state['total_pnl_pct'],
            total_trades=state['total_trades'],
            win_rate=state['win_rate'],
            is_paper=True,
        )
        return snapshot
