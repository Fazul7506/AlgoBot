"""Canonical persisted market-data access for all research surfaces.

Research code must consume the normalized Candle store rather than fetching
fresh broker history. This keeps analysis, indicators, strategies, AI training,
backtesting and replay reproducible from the same database snapshot.
"""
from __future__ import annotations

from typing import Any

from apps.market_data.constants import TIMEFRAMES
from apps.market_data.historical import normalize_timeframe
from apps.market_data.models import Candle, MarketSymbol


class ResearchDataService:
    """Read-only access to the persisted canonical research dataset."""

    def market(self, symbol: str) -> MarketSymbol:
        value = str(symbol or "").strip().upper()
        market = MarketSymbol.objects.filter(
            symbol=value,
            is_active=True,
            is_tradable=True,
        ).first()
        if not market:
            raise ValueError(f"Unknown active tradable market symbol: {value}")
        return market

    def timeframe(self, value: str | None) -> str:
        return normalize_timeframe(value)

    def candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 300,
        start_epoch: int | None = None,
        end_epoch: int | None = None,
    ) -> list[dict[str, Any]]:
        canonical = self.timeframe(timeframe)
        market = self.market(symbol)
        limit = min(max(int(limit), 1), 10000)
        qs = Candle.objects.filter(symbol=market, timeframe=canonical)
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
    ) -> list[dict[str, Any]]:
        return self.candles(
            symbol,
            timeframe,
            limit=10000,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
        )

    def count(
        self,
        symbol: str,
        timeframe: str = "1m",
        start_epoch: int | None = None,
        end_epoch: int | None = None,
    ) -> int:
        canonical = self.timeframe(timeframe)
        market = self.market(symbol)
        qs = Candle.objects.filter(symbol=market, timeframe=canonical)
        if start_epoch is not None:
            qs = qs.filter(epoch__gte=int(start_epoch))
        if end_epoch is not None:
            qs = qs.filter(epoch__lte=int(end_epoch))
        return qs.count()

    def coverage(self, symbol: str, timeframe: str = "1m") -> dict[str, Any]:
        canonical = self.timeframe(timeframe)
        market = self.market(symbol)
        qs = Candle.objects.filter(symbol=market, timeframe=canonical)
        first = qs.order_by("epoch", "id").values_list("epoch", flat=True).first()
        last = qs.order_by("-epoch", "-id").values_list("epoch", flat=True).first()
        count = qs.count()
        return {
            "symbol": market.symbol,
            "timeframe": canonical,
            "count": count,
            "first_epoch": first,
            "last_epoch": last,
            "source": "market_data.Candle",
            "ready": count > 0,
        }

    def supported_timeframes(self) -> list[str]:
        return list(TIMEFRAMES.keys())

    def latest(self, symbol: str, timeframe: str = "1m") -> dict[str, Any] | None:
        rows = self.candles(symbol, timeframe, limit=1)
        return rows[-1] if rows else None
