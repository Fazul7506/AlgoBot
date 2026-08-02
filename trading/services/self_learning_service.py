"""
Service layer for the self-learning trading engine.
"""
from typing import Dict, List, Optional
from trading.models.core import Strategy
from trading.ai.learning_engine import SelfLearningEngine, TradePatternRecognizer


class SelfLearningService:
    def __init__(self):
        self.engine = SelfLearningEngine()
        self.pattern_recognizer = TradePatternRecognizer()

    def evaluate_model_performance(
        self,
        symbol: str,
        timeframe: str,
        strategy_name: Optional[str] = None,
        days: int = 90,
    ) -> Dict[str, object]:
        return self.engine.analyze(symbol, timeframe, strategy_name=strategy_name, days=days)

    def refresh_strategy_metrics(
        self,
        strategy_name: str,
        days: int = 90,
    ) -> Dict[str, object]:
        summary = self.pattern_recognizer.analyze_closed_trades(
            strategy_name=strategy_name,
            days=days,
        )

        strategy = Strategy.objects.filter(name__iexact=strategy_name).first()
        updated = False
        if strategy:
            strategy.total_trades = summary['total_trades']
            strategy.winning_trades = summary['wins']
            strategy.losing_trades = summary['losses']
            strategy.win_rate = round(summary['win_rate'] * 100.0, 2)
            strategy.total_pnl = summary['total_pnl']
            strategy.save(update_fields=['total_trades', 'winning_trades', 'losing_trades', 'win_rate', 'total_pnl'])
            updated = True

        return {
            'strategy_name': strategy_name,
            'updated': updated,
            'strategy_exists': bool(strategy),
            'summary': summary,
        }

    def review_and_retrain(
        self,
        symbol: str,
        timeframe: str,
        strategy_name: Optional[str] = None,
        days: int = 90,
        window: int = 200,
        horizon: int = 1,
        min_win_rate: float = 0.45,
        max_model_age_days: int = 14,
        model_types: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, object]:
        result = self.engine.review_and_retrain(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            days=days,
            window=window,
            horizon=horizon,
            min_win_rate=min_win_rate,
            max_model_age_days=max_model_age_days,
            model_types=model_types,
            force=force,
        )

        if strategy_name:
            self.refresh_strategy_metrics(strategy_name, days=days)

        return result
