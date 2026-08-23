"""Compatibility facade for the retired trading.DerivAccount model."""
from datetime import timedelta
from django.utils import timezone

from apps.brokers.models import BrokerAccount


def _kwargs(kwargs):
    values = dict(kwargs)
    values["broker__broker_type"] = "deriv"
    return values


class _DerivAccountProxy:
    def __init__(self, account):
        self._account = account

    def __getattr__(self, name):
        if name == "account_type":
            return (self._account.credentials or {}).get("account_type", "demo")
        if name == "needs_refresh":
            return bool(self._account.expires_at and self._account.expires_at - timedelta(minutes=5) <= timezone.now())
        return getattr(self._account, name)

    def __setattr__(self, name, value):
        if name == "_account":
            object.__setattr__(self, name, value)
        elif name == "account_type":
            credentials = dict(self._account.credentials or {})
            credentials["account_type"] = value
            self._account.credentials = credentials
        else:
            setattr(self._account, name, value)

    def set_access_token(self, token): return self._account.set_access_token(token)
    def get_access_token(self): return self._account.get_access_token()
    def set_refresh_token(self, token): return self._account.set_refresh_token(token)
    def get_refresh_token(self): return self._account.get_refresh_token()
    def save(self, *args, **kwargs): return self._account.save(*args, **kwargs)


class _DerivAccountManager:
    def get(self, *args, **kwargs):
        return _DerivAccountProxy(BrokerAccount.objects.get(*args, **_kwargs(kwargs)))

    def filter(self, *args, **kwargs):
        return BrokerAccount.objects.filter(*args, **_kwargs(kwargs))

    def get_or_create(self, *args, **kwargs):
        account, created = BrokerAccount.objects.get_or_create(*args, **_kwargs(kwargs))
        return _DerivAccountProxy(account), created


class DerivAccount:
    """Deprecated compatibility symbol; no database model is declared here."""
    objects = _DerivAccountManager()
    DoesNotExist = BrokerAccount.DoesNotExist
