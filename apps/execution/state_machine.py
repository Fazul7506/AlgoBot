from __future__ import annotations

from dataclasses import dataclass
from django.db import transaction
from trading.models import Trade, TradeStateTransition


@dataclass(frozen=True)
class TransitionResult:
    trade: Trade
    from_state: str
    to_state: str


class TradeStateMachine:
    """Persists explicit trade lifecycle transitions and blocks invalid jumps."""

    allowed = {
        "NEW": {"VALIDATED", "CANCELLED"},
        "VALIDATED": {"QUEUED", "CANCELLED"},
        "QUEUED": {"SUBMITTED", "CANCELLED"},
        "SUBMITTED": {"ACCEPTED", "CANCELLED"},
        "ACCEPTED": {"OPEN", "CANCELLED"},
        "OPEN": {"PARTIALLY_CLOSED", "CLOSED"},
        "PARTIALLY_CLOSED": {"CLOSED"},
        "CLOSED": {"ARCHIVED"},
        "ARCHIVED": set(),
        "CANCELLED": {"ARCHIVED"},
    }

    @transaction.atomic
    def transition(self, trade: Trade, to_state: str, *, reason: str = "", metadata: dict | None = None) -> TransitionResult:
        from_state = trade.status
        if to_state not in self.allowed.get(from_state, set()):
            raise ValueError(f"Invalid trade transition {from_state} -> {to_state}")
        trade.status = to_state
        trade.save(update_fields=["status"])
        TradeStateTransition.objects.create(trade=trade, from_state=from_state, to_state=to_state, reason=reason, metadata=metadata or {})
        return TransitionResult(trade=trade, from_state=from_state, to_state=to_state)
