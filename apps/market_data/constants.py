from __future__ import annotations

SUPPORTED_MARKETS = [
    "Volatility Indices", "Boom", "Crash", "Forex", "Crypto", "Derived Indices",
    "Jump Indices", "Commodities", "Stock Indices",
]
TIMEFRAMES = {
    "tick": 0, "1s": 1, "5s": 5, "15s": 15, "30s": 30, "1m": 60, "2m": 120,
    "5m": 300, "10m": 600, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}
EVENT_TICK_RECEIVED = "TickReceived"
EVENT_NEW_CANDLE = "NewCandle"
EVENT_MARKET_OPENED = "MarketOpened"
EVENT_MARKET_CLOSED = "MarketClosed"
EVENT_SYMBOL_UPDATED = "SymbolUpdated"
EVENT_SUBSCRIPTION_ADDED = "SubscriptionAdded"
EVENT_SUBSCRIPTION_REMOVED = "SubscriptionRemoved"
EVENT_REPLAY_STARTED = "ReplayStarted"
EVENT_REPLAY_STOPPED = "ReplayStopped"
