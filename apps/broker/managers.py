"""Compatibility facade for the canonical broker registry."""
from apps.brokers.services import BrokerManager as CanonicalBrokerManager, BrokerRegistry


class BrokerManager(CanonicalBrokerManager):
    def get_adapter(self, account):
        return BrokerRegistry().adapter(account.broker, account)

    def register_adapter(self, slug: str, dotted_path: str) -> None:
        BrokerRegistry().register(slug, dotted_path)
