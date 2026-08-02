"""
Advanced analytics service for Phase 12 performance tracking and reporting.
"""
from io import BytesIO
from datetime import timedelta
from typing import Any, Dict, List, Optional
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from trading.models.core import Trade, Strategy
from trading.services.strategy_service import StrategyService
from trading.services.paper_vs_live_comparison import PaperVsLiveComparison
from trading.analytics.metrics import win_rate, profit_factor, roi

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class AdvancedAnalyticsService:
    DEFAULT_INITIAL_BALANCE = 1000.0

    def _filter_trades(
        self,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        days: int = 90,
        user=None,
    ):
        trades = Trade.objects.filter(status='CLOSED')
        if user is not None:
            trades = trades.filter(user=user)
        if symbol:
            trades = trades.filter(symbol__iexact=symbol)
        if strategy_name:
            trades = trades.filter(strategy__iexact=strategy_name)
        if days is not None:
            cutoff = timezone.now() - timedelta(days=days)
            trades = trades.filter(closed_at__gte=cutoff)
        return trades.order_by('closed_at')

    def compute_performance_metrics(
        self,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        days: int = 90,
        user=None,
        initial_balance: Optional[float] = None,
    ) -> Dict[str, Any]:
        trades = self._filter_trades(symbol=symbol, strategy_name=strategy_name, days=days, user=user)
        total_trades = trades.count()
        wins = trades.filter(profit__gt=0).count()
        losses = trades.filter(profit__lte=0).count()
        total_pnl = trades.aggregate(total_pnl=Sum('profit'))['total_pnl'] or 0.0
        avg_pnl = trades.aggregate(avg_pnl=Avg('profit'))['avg_pnl'] or 0.0
        gross_profit = trades.filter(profit__gt=0).aggregate(Sum('profit'))['profit__sum'] or 0.0
        gross_loss = abs(trades.filter(profit__lt=0).aggregate(Sum('profit'))['profit__sum'] or 0.0)

        starting_balance = initial_balance or self.DEFAULT_INITIAL_BALANCE
        ending_balance = starting_balance + float(total_pnl)

        metrics = {
            'symbol': symbol,
            'strategy_name': strategy_name,
            'days': days,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate(wins, losses), 2),
            'total_pnl': round(float(total_pnl), 2),
            'avg_pnl': round(float(avg_pnl), 2),
            'profit_factor': round(profit_factor([t.profit for t in trades]), 4),
            'roi': round(roi(starting_balance, ending_balance), 2),
            'starting_balance': round(starting_balance, 2),
            'ending_balance': round(ending_balance, 2),
            'equity_curve': self.equity_curve(trades, starting_balance=starting_balance),
            'monthly_profits': self.monthly_profit_summary(trades),
        }

        return metrics

    def equity_curve(self, trades, starting_balance: float = DEFAULT_INITIAL_BALANCE) -> List[Dict[str, Any]]:
        curve = []
        balance = starting_balance
        for trade in trades:
            balance += float(trade.profit or 0.0)
            curve.append({
                'closed_at': trade.closed_at.isoformat() if trade.closed_at else None,
                'equity': round(balance, 2),
                'profit': round(float(trade.profit or 0.0), 2),
                'symbol': trade.symbol,
                'strategy': trade.strategy,
            })
        return curve

    def monthly_profit_summary(self, trades) -> Dict[str, float]:
        summary = {}
        for trade in trades:
            if not trade.closed_at:
                continue
            month = trade.closed_at.strftime('%Y-%m')
            summary[month] = summary.get(month, 0.0) + float(trade.profit or 0.0)
        return {month: round(amount, 2) for month, amount in sorted(summary.items())}

    def strategy_comparison(
        self,
        strategy_names: Optional[List[str]] = None,
        symbol: str = 'R_75',
        timeframe: str = 'M1',
    ) -> List[Dict[str, Any]]:
        return StrategyService.compare_strategies(strategy_names=strategy_names, symbol=symbol, timeframe=timeframe)

    def export_performance_csv(
        self,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        days: int = 90,
        user=None,
        initial_balance: Optional[float] = None,
    ) -> str:
        metrics = self.compute_performance_metrics(
            symbol=symbol,
            strategy_name=strategy_name,
            days=days,
            user=user,
            initial_balance=initial_balance,
        )

        headers = [
            'symbol', 'strategy_name', 'days', 'total_trades', 'wins', 'losses',
            'win_rate', 'total_pnl', 'avg_pnl', 'profit_factor', 'roi',
            'starting_balance', 'ending_balance'
        ]
        rows = [','.join(headers)]
        values = [
            metrics.get('symbol') or '',
            metrics.get('strategy_name') or '',
            str(metrics.get('days', 0)),
            str(metrics.get('total_trades', 0)),
            str(metrics.get('wins', 0)),
            str(metrics.get('losses', 0)),
            str(metrics.get('win_rate', 0)),
            str(metrics.get('total_pnl', 0)),
            str(metrics.get('avg_pnl', 0)),
            str(metrics.get('profit_factor', 0)),
            str(metrics.get('roi', 0)),
            str(metrics.get('starting_balance', 0)),
            str(metrics.get('ending_balance', 0)),
        ]
        rows.append(','.join(values))
        rows.append('')
        rows.append('Month,Profit')
        for month, profit in metrics.get('monthly_profits', {}).items():
            rows.append(f"{month},{profit}")
        return '\n'.join(rows)

    def export_strategy_comparison_csv(
        self,
        strategy_names: Optional[List[str]] = None,
        symbol: str = 'R_75',
        timeframe: str = 'M1',
    ) -> str:
        comparison = self.strategy_comparison(strategy_names=strategy_names, symbol=symbol, timeframe=timeframe)
        headers = [
            'strategy', 'total_trades', 'wins', 'losses', 'win_rate',
            'profit_factor', 'sharpe_ratio', 'total_profit', 'roi'
        ]
        rows = [','.join(headers)]
        for item in comparison:
            result = item.get('result', {})
            rows.append(','.join([
                item.get('strategy', ''),
                str(result.get('total_trades', 0)),
                str(result.get('wins', 0)),
                str(result.get('losses', 0)),
                str(result.get('win_rate', 0)),
                str(result.get('profit_factor', 0)),
                str(result.get('sharpe_ratio', 0)),
                str(result.get('total_profit', 0)),
                str(result.get('roi', 0)),
            ]))
        return '\n'.join(rows)

    def export_pdf(
        self,
        report_title: str,
        report_rows: List[List[Any]],
        report_metadata: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        if not PDF_AVAILABLE:
            raise ImportError('PDF export requires reportlab. Install reportlab to enable PDF reports.')

        buffer = BytesIO()
        page = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        page.setFont('Helvetica-Bold', 16)
        page.drawString(40, height - 40, report_title)
        page.setFont('Helvetica', 10)
        y = height - 70

        if report_metadata:
            for key, value in report_metadata.items():
                page.drawString(40, y, f"{key}: {value}")
                y -= 14
            y -= 10

        page.setFont('Helvetica-Bold', 10)
        for col_index, col_name in enumerate(report_rows[0]):
            page.drawString(40 + col_index * 100, y, str(col_name))
        page.setFont('Helvetica', 10)
        y -= 16

        for row in report_rows[1:]:
            if y < 40:
                page.showPage()
                y = height - 40
                page.setFont('Helvetica-Bold', 10)
                for col_index, col_name in enumerate(report_rows[0]):
                    page.drawString(40 + col_index * 100, y, str(col_name))
                y -= 16
                page.setFont('Helvetica', 10)
            for col_index, value in enumerate(row):
                page.drawString(40 + col_index * 100, y, str(value))
            y -= 14

        page.save()
        buffer.seek(0)
        return buffer.read()
