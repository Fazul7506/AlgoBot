"""Compatibility facade for the retired broker service layer.

All broker state and execution now live in apps.brokers.
"""
from apps.brokers.models import BrokerAccount, BrokerConnectionLog
from apps.brokers.services import BrokerManager, BrokerRegistry, BrokerConnectionService as CanonicalConnectionService, AuthenticationService, SynchronizationService


class BrokerService:
    def __init__(self, manager=None):
        self.manager = manager or BrokerManager()

    def _adapter(self, account):
        return BrokerRegistry().adapter(account.broker, account)

    async def buy(self, account, **payload):
        return await self._adapter(account).place_order(payload)

    async def sell(self, account, **payload):
        return await self._adapter(account).place_order(payload)

    async def balance(self, account):
        return await self._adapter(account).get_balance()

    async def history(self, account, **filters):
        return await self._adapter(account).get_trade_history(**filters)

    async def positions(self, account):
        return await self._adapter(account).get_positions()

    async def orders(self, account):
        return await self._adapter(account).get_orders()

    async def subscribe_ticks(self, account, symbol):
        return await self._adapter(account).subscribe_ticks(symbol)


class BrokerHealthService:
    def record(self, account, status, event, latency=None):
        return BrokerConnectionLog.objects.create(broker_account=account, status=status, event=event, latency=latency)

    def latest(self, account):
        return account.connection_logs.first()


class BrokerConnectionService(CanonicalConnectionService):
    pass


class BrokerAuthenticationService(AuthenticationService):
    def store_token(self, account, access_token, refresh_token="", expires_at=None):
        account.set_access_token(access_token)
        account.set_refresh_token(refresh_token)
        account.expires_at = expires_at
        account.token_status = "active"
        account.save(update_fields=["access_token", "refresh_token", "expires_at", "token_status"])
        return account


class BrokerSynchronizationService(SynchronizationService):
    pass


class BrokerMonitoringService:
    def unhealthy_accounts(self):
        return BrokerAccount.objects.exclude(status="active")


__all__ = [
    "BrokerService", "BrokerHealthService", "BrokerConnectionService",
    "BrokerAuthenticationService", "BrokerSynchronizationService", "BrokerMonitoringService",
    "BrokerRegistry", "BrokerManager",
]
