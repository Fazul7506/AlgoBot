from django.utils import timezone
from .managers import BrokerManager
from .models import BrokerAccount, BrokerConnectionLog, BrokerToken
from .repositories import BrokerRepository


class BrokerService:
    def __init__(self, manager: BrokerManager | None = None): self.manager = manager or BrokerManager()
    async def buy(self, account: BrokerAccount, **payload): return await self.manager.get_adapter(account).buy(**payload)
    async def sell(self, account: BrokerAccount, **payload): return await self.manager.get_adapter(account).sell(**payload)
    async def balance(self, account: BrokerAccount): return await self.manager.get_adapter(account).balance()
    async def history(self, account: BrokerAccount, **filters): return await self.manager.get_adapter(account).history(**filters)
    async def positions(self, account: BrokerAccount): return await self.manager.get_adapter(account).positions()
    async def orders(self, account: BrokerAccount): return await self.manager.get_adapter(account).orders()
    async def subscribe_ticks(self, account: BrokerAccount, symbol: str): return await self.manager.get_adapter(account).subscribe_ticks(symbol)


class BrokerHealthService:
    def record(self, account: BrokerAccount, status: str, event: str, latency: float | None = None):
        return BrokerConnectionLog.objects.create(broker_account=account, status=status, event=event, latency=latency)
    def latest(self, account: BrokerAccount): return account.connection_logs.first()


class BrokerConnectionService:
    async def connect(self, account: BrokerAccount):
        """Connect the broker and immediately hydrate the account with live broker state."""
        adapter = BrokerManager().get_adapter(account)
        await adapter.connect()
        account.is_connected = True
        account.save(update_fields=["is_connected"])
        await BrokerSynchronizationService().sync_balance(account)
        BrokerHealthService().record(account, "connected", "live account authorised")
        return account

    async def disconnect(self, account: BrokerAccount):
        await BrokerManager().get_adapter(account).disconnect()
        account.is_connected = False
        account.save(update_fields=["is_connected"])
        BrokerHealthService().record(account, "disconnected", "broker disconnected")
        return account


class BrokerAuthenticationService:
    def store_token(self, account: BrokerAccount, access_token: str, refresh_token: str = "", expires_at=None):
        token, _ = BrokerToken.objects.get_or_create(broker_account=account)
        token.set_access_token(access_token); token.set_refresh_token(refresh_token); token.expires_at = expires_at; token.status = "active"; token.last_refresh = timezone.now(); token.save(); return token
    async def refresh(self, account: BrokerAccount): return await BrokerManager().get_adapter(account).refresh_token()


class BrokerSynchronizationService:
    async def sync_balance(self, account: BrokerAccount):
        data = await BrokerService().balance(account)
        if isinstance(data, dict) and isinstance(data.get("balance"), dict):
            data = data["balance"]
        account.balance = data.get("balance", account.balance)
        account.currency = data.get("currency", account.currency)
        account.equity = data.get("equity", account.balance)
        account.save(update_fields=["balance", "currency", "equity"])
        return data


class BrokerMonitoringService:
    def unhealthy_accounts(self): return BrokerAccount.objects.filter(is_connected=False)

BrokerRepository = BrokerRepository
