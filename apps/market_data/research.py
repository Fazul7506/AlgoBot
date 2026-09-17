"""Canonical market-data access for historical research surfaces.

Research consumers must read broker-ingested Candle rows and must not reach out
through a broker adapter while evaluating historical data.  Raw ticks are
materialized as first-class ``Candle(timeframe='tick')`` rows by the market-data
pipeline, so every research timeframe can share the same canonical interface.
"""
from __future__ import annotations

from typing import Any

from .constants import TIMEFRAMES
from .historical import normalize_timeframe
from .models import Candle, MarketSymbol


class ResearchCandleStore:
    """Read-only access to the persisted canonical candle database."""

    @staticmethod
    def timeframe(value: str | None) -> str:
        return normalize_timeframe(value)

    @staticmethod
    def market(symbol: str) -> MarketSymbol:
        value = str(symbol or "").strip().upper()
        market = MarketSymbol.objects.filter(
            symbol=value,
            is_active=True,
            is_tradable=True,
        ).first()
        if market is None:
            raise ValueError(f"Unknown active tradable market symbol: {value}")
        return market

    @classmethod
    def candles(
        cls,
        symbol: str,
        timeframe: str = "1m",
        *,
        start_epoch: int | None = None,
        end_epoch: int | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        canonical = cls.timeframe(timeframe)
        market = cls.market(symbol)
        qs = Candle.objects.filter(symbol=market, timeframe=canonical)
        if start_epoch is not None:
            qs = qs.filter(epoch__gte=int(start_epoch))
        if end_epoch is not None:
            qs = qs.filter(epoch__lte=int(end_epoch))
        bounded_limit = max(1, min(int(limit), 5000))
        return list(
            qs.order_by("epoch", "id")[:bounded_limit].values(
                "epoch", "open", "high", "low", "close", "volume"
            )
        )

    @classmethod
    def count(
        cls,
        symbol: str,
        timeframe: str = "1m",
        *,
        start_epoch: int | None = None,
        end_epoch: int | None = None,
    ) -> int:
        canonical = cls.timeframe(timeframe)
        market = cls.market(symbol)
        qs = Candle.objects.filter(symbol=market, timeframe=canonical)
        if start_epoch is not None:
            qs = qs.filter(epoch__gte=int(start_epoch))
        if end_epoch is not None:
            qs = qs.filter(epoch__lte=int(end_epoch))
        return qs.count()

    @classmethod
    def coverage(cls, symbol: str, timeframe: str = "1m") -> dict[str, Any]:
        canonical = cls.timeframe(timeframe)
        market = cls.market(symbol)
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

    @staticmethod
    def supported_timeframes() -> list[str]:
        return list(TIMEFRAMES.keys())
