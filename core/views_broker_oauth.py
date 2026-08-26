"""Shared Deriv OAuth account helpers.

The browser callback lives exclusively in ``views_deriv_oauth_safe``. This
module contains only reusable account parsing/persistence helpers so there is
one canonical OAuth entry point and one canonical live-connection path.
"""

from django.utils import timezone

from apps.brokers.models import BrokerAccount, BrokerConnection


def _account_records(payload: dict) -> list[dict]:
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if isinstance(data, dict):
        data = [data]
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _select_account(payload: dict) -> dict | None:
    accounts = _account_records(payload)
    return accounts[0] if accounts else None


def _account_id(record: dict) -> str:
    return str(record.get("account_id") or record.get("loginid") or "").strip()


def _account_type(record: dict, websocket_balance: dict | None = None) -> str:
    websocket_balance = websocket_balance or {}
    value = str(record.get("account_type") or "").lower().strip()
    if value in {"real", "demo"}:
        return value
    if record.get("is_virtual") is True or websocket_balance.get("is_virtual") is True:
        return "demo"
    return "real"


def _persist_deriv_account(*, user, broker, record, access_token, refresh_token, expires_at, preferred=False, websocket_balance=None, websocket_health="not_checked"):
    """Persist one Deriv account returned by OAuth without dropping siblings."""
    account_id = _account_id(record)
    if not account_id:
        return None
    websocket_balance = websocket_balance or {}
    currency = record.get("currency") or websocket_balance.get("currency") or "USD"
    balance_value = record.get("balance") if record.get("balance") is not None else websocket_balance.get("balance") or 0
    avatar_url = str(record.get("avatar_url") or websocket_balance.get("avatar_url") or "").strip()
    account_type = _account_type(record, websocket_balance)

    broker_account, _ = BrokerAccount.objects.get_or_create(broker=broker, account_id=account_id, defaults={"user": user})
    broker_account.user = user
    broker_account.currency = currency
    broker_account.balance = balance_value
    broker_account.equity = websocket_balance.get("equity") if websocket_balance.get("equity") is not None else balance_value
    broker_account.status = "active"
    broker_account.is_preferred = preferred
    broker_account.credentials = {
        **(broker_account.credentials or {}),
        "account_type": account_type,
        "connection_health": websocket_health,
        **({"avatar_url": avatar_url} if avatar_url else {}),
    }
    broker_account.set_access_token(access_token)
    broker_account.set_refresh_token(refresh_token or "")
    broker_account.expires_at = expires_at
    broker_account.token_status = "active"
    broker_account.last_refresh = timezone.now()
    broker_account.last_synced_at = timezone.now()
    broker_account.save()

    BrokerConnection.objects.update_or_create(
        broker_account=broker_account,
        defaults={
            "broker": broker,
            "status": "connected" if websocket_health == "verified" else "degraded",
            "last_ping": timezone.now() if websocket_health == "verified" else None,
            "connected_at": timezone.now(),
            "heartbeat": {"oauth_verified": True, "websocket_health": websocket_health},
        },
    )
    return broker_account
