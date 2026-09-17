"""Canonical persisted market-data access for all research surfaces.

Research code must consume the normalized Candle store rather than fetching
fresh broker history. This keeps analysis, indicators, strategies, AI training,
backtesting and replay reproducible from the same database snapshot.
"""
from __future__ import annotations

from apps.market_data.historical import normalize_timeframe
from apps.market_data.models import Candle, MarketSymbol


class ResearchDataService:
    """Read-only access to the persisted canonical research dataset."""

    def market(self, symbol: str) -> MarketSymbol:
        market = MarketSymbol.objects.filter(
            symbol=str(symbol).strip().upper(), is_active=True
        ).first()
        if not market:
            raise ValueError(f"Unknown active market symbol: {symbol}")
        return market

    def candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 300,
        start_epoch: int | None = None,
        end_epoch: int | None = None,
    ) -> list[dict]:
        timeframe = normalize_timeframe(timeframe)
        market = self.market(symbol)
        limit = min(max(int(limit), 1), 10000)
        qs = Candle.objects.filter(symbol=market, timeframe=timeframe)
        if start_epoch is not None:
            qs = qs.filter(epoch__gte=int(start_epoch))
        if end_epoch is not None:
            qs = qs.filter(epoch__lte=int(end_epoch))
        rows = list(
            qs.order_by("-epoch", "-id")
            .values("open", "high", "low", "close", "volume", "epoch")[:limit]
        )
        rows.reverse()
        return rows

    def candles_for_range(
        self,
        symbol: str,
        timeframe: str,
        start_epoch: int,
        end_epoch: int,
    ) -> list[dict]:
        return self.candles(
            symbol,
            timeframe,
            limit=10000,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
        )

    def latest(self, symbol: str, timeframe: str = "1m") -> dict | None:
        rows = self.candles(symbol, timeframe, limit=1)
        return rows[-1] if rows else None
