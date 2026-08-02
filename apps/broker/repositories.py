from .models import Broker, BrokerAccount, BrokerConnectionLog, BrokerToken


class BrokerRepository:
    """Persistence gateway for broker entities."""
    def brokers(self): return Broker.objects.all()
    def accounts_for_user(self, user): return BrokerAccount.objects.filter(user=user).select_related("broker")
    def default_account(self, user): return self.accounts_for_user(user).filter(is_default=True).first()
    def log(self, account, status: str, event: str, latency: float | None = None):
        return BrokerConnectionLog.objects.create(broker_account=account, status=status, event=event, latency=latency)
    def token_for_account(self, account): return BrokerToken.objects.filter(broker_account=account).first()
