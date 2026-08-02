from trading.models import Signal


class SignalService:

    @staticmethod
    def create_signal(
        symbol,
        strategy,
        direction,
        confidence=50,
        timeframe=None,
        indicators=None,
        market_regime=None,
    ):
        # `strategy` may be a name (string) or a Strategy instance
        kwargs = {
            'symbol': symbol,
            'direction': direction,
            'confidence': confidence,
        }

        if timeframe:
            kwargs['timeframe'] = timeframe

        if indicators:
            kwargs['indicators_used'] = indicators

        if market_regime:
            kwargs['market_regime'] = market_regime

        # If strategy is object with 'id', assume it's a Strategy instance
        try:
            if hasattr(strategy, 'id'):
                kwargs['strategy_fk'] = strategy
            else:
                # name string -> legacy char field on Signal
                kwargs['strategy'] = str(strategy)
        except Exception:
            kwargs['strategy'] = str(strategy)

        return Signal.objects.create(**kwargs)