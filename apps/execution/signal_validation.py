from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


class SignalValidationService:
    """Dedicated pre-trade validation layer kept separate from risk approval."""

    def validate(self, *, signal: dict, account=None, strategy=None, websocket_connected: bool = False, trading_enabled: bool = False) -> ValidationResult:
        errors: list[str] = []
        if not trading_enabled:
            errors.append("Trading is disabled")
        if not websocket_connected:
            errors.append("Websocket is not connected")
        if not account:
            errors.append("Account is not authenticated")
        elif not getattr(account, "is_connected", False):
            errors.append("Broker account is not connected")
        if account and getattr(account, "balance", 0) <= 0:
            errors.append("Account balance is unavailable or zero")
        if strategy is not None and not getattr(strategy, "is_active", True):
            errors.append("Strategy is disabled")
        if not signal.get("symbol"):
            errors.append("Market symbol is required")
        if not signal.get("direction"):
            errors.append("Signal direction is required")
        return ValidationResult(is_valid=not errors, errors=errors, context={"symbol": signal.get("symbol"), "direction": signal.get("direction")})
