"""
Management command to trigger self-learning retraining and model comparison.
Usage: python manage.py retrain_models --symbol R_50 --timeframe M1
"""
import json
from django.core.management.base import BaseCommand
from trading.services.self_learning_service import SelfLearningService


class Command(BaseCommand):
    help = 'Run self-learning retraining and strategy performance review.'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', required=True)
        parser.add_argument('--timeframe', default='M1')
        parser.add_argument('--strategy', default=None)
        parser.add_argument('--window', type=int, default=200)
        parser.add_argument('--horizon', type=int, default=1)
        parser.add_argument('--days', type=int, default=30)
        parser.add_argument('--min_win_rate', type=float, default=0.45)
        parser.add_argument('--max_model_age_days', type=int, default=14)
        parser.add_argument('--model_types', default='rf,xgb,lgb')
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        symbol = options['symbol']
        timeframe = options['timeframe']
        strategy_name = options['strategy']
        window = options['window']
        horizon = options['horizon']
        days = options['days']
        min_win_rate = options['min_win_rate']
        max_model_age_days = options['max_model_age_days']
        model_types = [m.strip() for m in options['model_types'].split(',') if m.strip()]
        force = options['force']

        service = SelfLearningService()
        result = service.review_and_retrain(
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

        self.stdout.write(json.dumps(result, indent=2, default=str))
