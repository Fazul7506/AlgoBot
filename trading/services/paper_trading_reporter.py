"""
Paper Trading Report Generator
Generates daily and weekly performance reports for paper trading accounts.
"""

from django.utils import timezone
from django.db.models import Q, Sum, Avg, Count, Max, Min
from datetime import datetime, timedelta
from trading.models.core import Trade, PerformanceSnapshot


class PaperTradingReporter:
    """Generates daily and weekly reports for paper trading performance."""

    @staticmethod
    def get_daily_report(date=None):
        """
        Generate daily report for paper trades.
        
        Args:
            date: Date for report (default: today)
            
        Returns:
            Dict with daily metrics
        """
        if date is None:
            date = timezone.now().date()
        
        start = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        end = timezone.make_aware(datetime.combine(date, datetime.max.time()))
        
        trades = Trade.objects.filter(
            is_paper=True,
            closed_at__range=[start, end]
        )
        
        daily_pnl = trades.aggregate(Sum('profit'))['profit__sum'] or 0
        win_count = trades.filter(profit__gt=0).count()
        lose_count = trades.filter(profit__lt=0).count()
        total_count = trades.count()
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0
        
        avg_pnl = trades.aggregate(avg_profit=Avg('profit'))['avg_profit'] or 0

        largest_win = trades.aggregate(max_profit=Max('profit'))['max_profit'] or 0
        largest_loss = trades.aggregate(min_profit=Min('profit'))['min_profit'] or 0

        return {
            'date': date.isoformat(),
            'report_type': 'DAILY',
            'trades_closed': total_count,
            'trades_won': win_count,
            'trades_lost': lose_count,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(daily_pnl, 2),
            'avg_pnl_per_trade': round(avg_pnl, 2),
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'trades': [
                {
                    'symbol': t.symbol,
                    'direction': t.contract_type,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'pnl': t.profit,
                    'time': t.closed_at.isoformat(),
                }
                for t in trades
            ],
            'generated_at': timezone.now().isoformat(),
        }

    @staticmethod
    def get_weekly_report(week_start=None):
        """
        Generate weekly report for paper trades.
        
        Args:
            week_start: Start date of week (default: current week)
            
        Returns:
            Dict with weekly metrics
        """
        if week_start is None:
            today = timezone.now().date()
            week_start = today - timedelta(days=today.weekday())
        
        week_end = week_start + timedelta(days=6)
        
        start_dt = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(week_end, datetime.max.time()))
        
        trades = Trade.objects.filter(
            is_paper=True,
            closed_at__range=[start_dt, end_dt]
        )
        
        snapshots = PerformanceSnapshot.objects.filter(
            is_paper=True,
            created_at__range=[start_dt, end_dt]
        )
        
        weekly_pnl = trades.aggregate(Sum('profit'))['profit__sum'] or 0
        win_count = trades.filter(profit__gt=0).count()
        lose_count = trades.filter(profit__lt=0).count()
        total_count = trades.count()
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0
        
        avg_balance = snapshots.aggregate(avg_balance=Avg('balance'))['avg_balance'] or 0
        avg_equity = snapshots.aggregate(avg_equity=Avg('equity'))['avg_equity'] or 0
        max_drawdown = snapshots.aggregate(max_dd=Max('drawdown_pct'))['max_dd'] or 0
        
        return {
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            'report_type': 'WEEKLY',
            'trades_closed': total_count,
            'trades_won': win_count,
            'trades_lost': lose_count,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(weekly_pnl, 2),
            'avg_balance': round(avg_balance, 2),
            'avg_equity': round(avg_equity, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'trading_days': snapshots.values('created_at__date').distinct().count(),
            'daily_summaries': [
                PaperTradingReporter.get_daily_report(
                    snapshot['created_at__date']
                )
                for snapshot in snapshots.values('created_at__date').distinct()
            ],
            'generated_at': timezone.now().isoformat(),
        }

    @staticmethod
    def export_daily_report_csv(date=None):
        """Export daily report as CSV format."""
        report = PaperTradingReporter.get_daily_report(date)
        
        lines = [
            f"DAILY PAPER TRADING REPORT - {report['date']}",
            f"Generated: {report['generated_at']}",
            "",
            "SUMMARY",
            f"Trades Closed,{report['trades_closed']}",
            f"Trades Won,{report['trades_won']}",
            f"Trades Lost,{report['trades_lost']}",
            f"Win Rate (%),{report['win_rate']}",
            f"Total PnL,{report['total_pnl']}",
            f"Avg PnL/Trade,{report['avg_pnl_per_trade']}",
            f"Largest Win,{report['largest_win']}",
            f"Largest Loss,{report['largest_loss']}",
            "",
            "TRADES",
            "Symbol,Direction,Entry,Exit,PnL,Time",
        ]
        
        for trade in report['trades']:
            lines.append(
                f"{trade['symbol']},{trade['direction']},"
                f"{trade['entry_price']},{trade['exit_price']},"
                f"{trade['pnl']},{trade['time']}"
            )
        
        return "\n".join(lines)

    @staticmethod
    def export_weekly_report_csv(week_start=None):
        """Export weekly report as CSV format."""
        report = PaperTradingReporter.get_weekly_report(week_start)
        
        lines = [
            f"WEEKLY PAPER TRADING REPORT",
            f"Week: {report['week_start']} to {report['week_end']}",
            f"Generated: {report['generated_at']}",
            "",
            "SUMMARY",
            f"Total Trades,{report['trades_closed']}",
            f"Trades Won,{report['trades_won']}",
            f"Trades Lost,{report['trades_lost']}",
            f"Win Rate (%),{report['win_rate']}",
            f"Total PnL,{report['total_pnl']}",
            f"Avg Balance,{report['avg_balance']}",
            f"Avg Equity,{report['avg_equity']}",
            f"Max Drawdown (%),{report['max_drawdown_pct']}",
            f"Trading Days,{report['trading_days']}",
        ]
        
        return "\n".join(lines)


from django.db.models import Max, Min
