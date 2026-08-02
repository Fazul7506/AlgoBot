class MarketDataError(Exception):
    """Base market data exception."""

class ValidationError(MarketDataError):
    """Raised when incoming market data is malformed or unsafe."""

class ReplayError(MarketDataError):
    """Raised when replay state transitions are invalid."""
