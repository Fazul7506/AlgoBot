from django.core.management.base import BaseCommand
from trading.models.core import Strategy
from trading.strategies.strategy_service import StrategyService


class Command(BaseCommand):
    help = 'Run a backtest for a saved strategy using historical tick data.'

    def add_arguments(self, parser):
        parser.add_argument('--strategy', type=str, default='trend', help='Strategy name to backtest')
        parser.add_argument('--symbol', type=str, default='R_75', help='Symbol to backtest')

    def handle(self, *args, **options):
        name = options['strategy']
        symbol = options['symbol']
        strategy = Strategy.objects.filter(name=name).first()

        if not strategy:
            self.stdout.write(self.style.ERROR(f'Strategy {name} not found.'))
            return

        result = StrategyService.run_backtest(strategy, symbol=symbol)
        self.stdout.write(str(result))
