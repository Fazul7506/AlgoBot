from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from django.test import TestCase

from apps.backtesting.tasks import _warmup_start, _window_result
from apps.market_data.models import Candle, MarketSymbol


class HistoricalWindowTests(TestCase):
    def test_warmup_uses_history_before_selected_start(self):
        market = MarketSymbol.objects.create(
            broker='deriv',
            symbol='BOOM1000',
            display_name='Boom 1000 Index',
            market='synthetic',
        )
        start = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
        for index in range(20):
            Candle.objects.create(
                symbol=market,
                timeframe='15m',
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100 + index,
                epoch=int((start - timedelta(minutes=15 * (20 - index))).timestamp()),
            )
        Candle.objects.create(symbol=market, timeframe='15m', open=120, high=121, low=119, close=120, epoch=int(start.timestamp()))
        Candle.objects.create(symbol=market, timeframe='15m', open=121, high=122, low=120, close=121, epoch=int((start + timedelta(minutes=15)).timestamp()))

        backtest = SimpleNamespace(symbol='BOOM1000', timeframe='15m', mode='candle_close', start_date=start)
        assert _warmup_start(backtest) == start - timedelta(minutes=15 * 20)

    def test_window_result_excludes_warmup_trades_and_recomputes_metrics(self):
        result = _window_result(
            {
                'total_trades': 3,
                'trades': [
                    {'entry_epoch': 99, 'exit_epoch': 100, 'profit': 1},
                    {'entry_epoch': 101, 'exit_epoch': 102, 'profit': -1},
                    {'entry_epoch': 103, 'exit_epoch': 104, 'profit': 2},
                ],
            },
            start_epoch=101,
            end_epoch=104,
        )
        assert result['total_trades'] == 2
        assert result['wins'] == 1
        assert result['losses'] == 1
        assert result['total_profit'] == 1.0
        assert result['warmup_trade_count'] == 1
        assert result['evaluation_start_epoch'] == 101
        assert result['evaluation_end_epoch'] == 104
