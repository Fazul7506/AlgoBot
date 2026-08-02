from apps.deriv.adapter import DerivAdapter
from .models import BrokerAccount


class BrokerManager:
    """Factory for broker adapters; keeps vendor dependencies at the edge."""
    def get_adapter(self, account: BrokerAccount):
        if account.broker.slug == "deriv":
            return DerivAdapter(account)
        raise ValueError(f"Unsupported broker: {account.broker.slug}")
