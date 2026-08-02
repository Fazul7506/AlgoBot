"""
Trade analysis utilities for self-learning and pattern recognition.
"""
from collections import defaultdict
from datetime import timedelta
from typing import Dict, Optional
from django.db.models import Avg, Sum
from django.utils import timezone

from trading.models.core import Trade


class TradePatternRecognizer:
    """Analyze closed trade patterns and regime-specific performance."""

    @staticmethod
    def analyze_closed_trades(
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        days: int = 90,
    ) -> Dict[str, object]:
        trades = Trade.objects.filter(status='CLOSED')

        if symbol:
            trades = trades.filter(symbol__iexact=symbol)
        if strategy_name:
            trades = trades.filter(strategy__iexact=strategy_name)

        if days is not None:
            cutoff = timezone.now() - timedelta(days=days)
            trades = trades.filter(closed_at__gte=cutoff)

        total = trades.count()
        wins = trades.filter(profit__gt=0).count()
        losses = trades.filter(profit__lte=0).count()

        total_pnl = trades.aggregate(total_pnl=Sum('profit'))['total_pnl'] or 0.0
        avg_pnl = trades.aggregate(avg_pnl=Avg('profit'))['avg_pnl'] or 0.0
        avg_pct = trades.aggregate(avg_pct=Avg('profit_pct'))['avg_pct'] or 0.0

        win_rate = (wins / total) if total else 0.0

        regime_breakdown = defaultdict(lambda: {
            'count': 0,
            'wins': 0,
            'losses': 0,
            'pnl': 0.0,
            'avg_pnl': 0.0,
            'win_rate': 0.0,
        })
        direction_breakdown = {'BUY': 0, 'SELL': 0, 'OTHER': 0}

        for trade in trades:
            regime = 'unknown'
            if isinstance(trade.indicators_snapshot, dict):
                regime = trade.indicators_snapshot.get('market_regime') or regime

            stats = regime_breakdown[regime]
            stats['count'] += 1
            stats['pnl'] += float(trade.profit or 0.0)
            if trade.profit > 0:
                stats['wins'] += 1
            else:
                stats['losses'] += 1

            direction = 'BUY' if trade.contract_type == 'CALL' else 'SELL' if trade.contract_type == 'PUT' else 'OTHER'
            direction_breakdown[direction] = direction_breakdown.get(direction, 0) + 1

        for regime, stats in regime_breakdown.items():
            if stats['count']:
                stats['avg_pnl'] = stats['pnl'] / stats['count']
                stats['win_rate'] = stats['wins'] / stats['count']

        return {
            'symbol': symbol,
            'strategy_name': strategy_name,
            'days': days,
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 4),
            'total_pnl': round(float(total_pnl), 4),
            'avg_pnl': round(float(avg_pnl), 4),
            'avg_profit_pct': round(float(avg_pct), 4),
            'regime_breakdown': dict(regime_breakdown),
            'direction_breakdown': direction_breakdown,
        }


class TradePatternInsights:
    """Generate pattern insights from closed trades."""

    @staticmethod
    def summarize(insight_data: Dict[str, object]) -> Dict[str, object]:
        patterns = []
        for regime, stats in insight_data.get('regime_breakdown', {}).items():
            if stats.get('count', 0) >= 2:
                patterns.append({
                    'market_regime': regime,
                    'trade_count': stats['count'],
                    'win_rate': round(stats['win_rate'], 4),
                    'avg_pnl': round(stats['avg_pnl'], 4),
                })

        return {
            'overall_win_rate': insight_data.get('win_rate', 0.0),
            'best_regimes': sorted(patterns, key=lambda item: item['avg_pnl'], reverse=True)[:3],
            'direction_bias': insight_data.get('direction_breakdown', {}),
        }
