"""
Paper vs Live Trading Comparison Service
Compares performance metrics between paper trading and live trading.
"""

from django.db.models import Sum, Avg, Count, Q, Max, Min
from datetime import datetime, timedelta
from django.utils import timezone
from trading.models.core import Trade, Strategy, PerformanceSnapshot


class PaperVsLiveComparison:
    """Compares paper trading performance against live trading."""

    @staticmethod
    def get_strategy_comparison(strategy_name, days=30):
        """
        Compare strategy performance between paper and live accounts.
        
        Args:
            strategy_name: Strategy name to compare
            days: Number of days to compare
            
        Returns:
            Dict with side-by-side metrics
        """
        start_date = timezone.now() - timedelta(days=days)
        
        # Paper trades
        paper_trades = Trade.objects.filter(
            strategy=strategy_name,
            is_paper=True,
            opened_at__gte=start_date
        )
        
        # Live trades
        live_trades = Trade.objects.filter(
            strategy=strategy_name,
            is_paper=False,
            opened_at__gte=start_date
        )
        
        paper_stats = PaperVsLiveComparison._calculate_stats(paper_trades)
        live_stats = PaperVsLiveComparison._calculate_stats(live_trades)
        
        return {
            'strategy': strategy_name,
            'period_days': days,
            'start_date': start_date.isoformat(),
            'end_date': timezone.now().isoformat(),
            'paper': paper_stats,
            'live': live_stats,
            'comparison': {
                'pnl_diff': round(paper_stats['total_pnl'] - live_stats['total_pnl'], 2),
                'win_rate_diff': round(paper_stats['win_rate'] - live_stats['win_rate'], 2),
                'trades_count_diff': paper_stats['total_trades'] - live_stats['total_trades'],
                'avg_pnl_diff': round(paper_stats['avg_pnl_per_trade'] - live_stats['avg_pnl_per_trade'], 2),
                'paper_outperforms': paper_stats['total_pnl'] > live_stats['total_pnl'],
            },
        }

    @staticmethod
    def _calculate_stats(trades):
        """Calculate statistics for a trade queryset."""
        total = trades.count()
        
        if total == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl_per_trade': 0,
                'largest_win': 0,
                'largest_loss': 0,
                'profit_factor': 0,
            }
        
        wins = trades.filter(profit__gt=0)
        losses = trades.filter(profit__lt=0)
        
        total_pnl = trades.aggregate(Sum('profit'))['profit__sum'] or 0
        avg_pnl = trades.aggregate(Avg('profit'))['profit__avg'] or 0
        
        gross_profit = wins.aggregate(Sum('profit'))['profit__sum'] or 0
        gross_loss = abs(losses.aggregate(Sum('profit'))['profit__sum'] or 0)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
        
        win_rate = (wins.count() / total * 100) if total > 0 else 0
        
        return {
            'total_trades': total,
            'winning_trades': wins.count(),
            'losing_trades': losses.count(),
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(avg_pnl, 2),
            'largest_win': trades.aggregate(Max=Max('profit')).get('Max') or 0,
            'largest_loss': trades.aggregate(Min=Min('profit')).get('Min') or 0,
            'profit_factor': round(profit_factor, 2),
        }

    @staticmethod
    def get_account_comparison():
        """Compare overall paper vs live account performance."""
        paper_snapshots = PerformanceSnapshot.objects.filter(is_paper=True)
        live_snapshots = PerformanceSnapshot.objects.filter(is_paper=False)
        
        paper_metrics = {
            'avg_balance': round(paper_snapshots.aggregate(Avg('balance'))['balance__avg'] or 0, 2),
            'avg_equity': round(paper_snapshots.aggregate(Avg('equity'))['equity__avg'] or 0, 2),
            'avg_win_rate': round(paper_snapshots.aggregate(Avg('win_rate'))['win_rate__avg'] or 0, 2),
            'snapshots_count': paper_snapshots.count(),
        }
        
        live_metrics = {
            'avg_balance': round(live_snapshots.aggregate(Avg('balance'))['balance__avg'] or 0, 2),
            'avg_equity': round(live_snapshots.aggregate(Avg('equity'))['equity__avg'] or 0, 2),
            'avg_win_rate': round(live_snapshots.aggregate(Avg('win_rate'))['win_rate__avg'] or 0, 2),
            'snapshots_count': live_snapshots.count(),
        }
        
        return {
            'paper': paper_metrics,
            'live': live_metrics,
            'comparison': {
                'balance_diff': round(paper_metrics['avg_balance'] - live_metrics['avg_balance'], 2),
                'equity_diff': round(paper_metrics['avg_equity'] - live_metrics['avg_equity'], 2),
                'win_rate_diff': round(paper_metrics['avg_win_rate'] - live_metrics['avg_win_rate'], 2),
            },
        }

    @staticmethod
    def get_risk_adjusted_comparison(strategy_name, days=30):
        """
        Compare risk-adjusted returns between paper and live trading.
        
        Args:
            strategy_name: Strategy name
            days: Number of days
            
        Returns:
            Dict with Sharpe-like metrics
        """
        start_date = timezone.now() - timedelta(days=days)
        
        paper_trades = Trade.objects.filter(
            strategy=strategy_name,
            is_paper=True,
            opened_at__gte=start_date,
            status='CLOSED'
        )
        
        live_trades = Trade.objects.filter(
            strategy=strategy_name,
            is_paper=False,
            opened_at__gte=start_date,
            status='CLOSED'
        )
        
        paper_pnls = [t.profit for t in paper_trades]
        live_pnls = [t.profit for t in live_trades]
        
        paper_std = PaperVsLiveComparison._calculate_std(paper_pnls) if paper_pnls else 0
        live_std = PaperVsLiveComparison._calculate_std(live_pnls) if live_pnls else 0
        
        paper_mean = sum(paper_pnls) / len(paper_pnls) if paper_pnls else 0
        live_mean = sum(live_pnls) / len(live_pnls) if live_pnls else 0
        
        paper_sharpe = (paper_mean / paper_std) if paper_std > 0 else 0
        live_sharpe = (live_mean / live_std) if live_std > 0 else 0
        
        return {
            'strategy': strategy_name,
            'period_days': days,
            'paper': {
                'mean_pnl': round(paper_mean, 2),
                'std_pnl': round(paper_std, 2),
                'sharpe_like': round(paper_sharpe, 2),
                'trade_count': len(paper_pnls),
            },
            'live': {
                'mean_pnl': round(live_mean, 2),
                'std_pnl': round(live_std, 2),
                'sharpe_like': round(live_sharpe, 2),
                'trade_count': len(live_pnls),
            },
        }

    @staticmethod
    def _calculate_std(values):
        """Calculate standard deviation."""
        if not values:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


from django.db.models import Max, Min
