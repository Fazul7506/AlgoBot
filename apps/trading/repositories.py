"""Deprecated compatibility facade for the broker-owned Position model."""
from apps.brokers.models import Position

class PositionRepository:
    def open_for_order(self, order, entry_price=None, broker_contract=None):
        from apps.execution.services import PositionService
        return PositionService().open_position(order, entry_price=entry_price, broker_contract=broker_contract)

    def open(self):
        return Position.objects.filter(status__in=["open", "active", "pending"])

    def closed(self):
        return Position.objects.filter(status__in=["closed", "expired", "settled"])
