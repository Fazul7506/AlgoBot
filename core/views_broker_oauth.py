"""Shared Deriv OAuth account helpers.

The browser callback lives exclusively in ``views_deriv_oauth_safe``. This
module contains only reusable account parsing, verification, and persistence
helpers so there is one canonical OAuth entry point and one canonical live-
connection path.
"""

import asyncio
import json

import requests
import websockets
from django.conf import settings
from django.utils import timezone

from apps.brokers.models import BrokerAccount, BrokerConnection
from apps.brokers.services import BrokerConnectionService
from core.services.oauth_service import DerivOAuthService


DERIV_ACCOUNTS_URL = settings.DERIV_OPTIONS_ACCOUNTS_URL


def _verify_authenticated_websocket(*args, **kwargs):
    """Compatibility hook for callers that optionally verify broker streams."""
    return None


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


def _verify_account(access_token: str) -> tuple[dict | None, list[dict]]:
    """Verify the OAuth credential and return the selected account plus all accounts."""
    headers = {"Authorization": f"Bearer {access_token}", "Deriv-App-ID": settings.DERIV_APP_ID, "Accept": "application/json"}
    try:
        response = requests.get(DERIV_ACCOUNTS_URL, headers=headers, timeout=(3.05, 10))
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 401:
            raise ValueError("Deriv rejected the OAuth access token") from exc
        if status == 403:
            raise ValueError("Deriv denied access to the trading account") from exc
        raise ValueError("Deriv account verification failed") from exc
    except (requests.RequestException, ValueError) as exc:
        raise ValueError("Deriv account verification is temporarily unavailable") from exc

    accounts = _account_records(payload)
    return _select_account(payload), accounts


async def _authorize_deriv_identity_async(access_token: str) -> dict:
    """Authorize a Deriv WebSocket and return the provider identity payload."""
    endpoint = getattr(settings, "DERIV_PUBLIC_WS_URL", "").strip()
    if not endpoint:
        raise ValueError("DERIV_PUBLIC_WS_URL is not configured")
    async with websockets.connect(
        endpoint,
        open_timeout=10,
        close_timeout=5,
        ping_interval=None,
    ) as ws:
        await ws.send(json.dumps({"authorize": access_token, "req_id": 1}))
        response = json.loads(await asyncio.wait_for(ws.recv(), 10))
    if response.get("error"):
        error = response["error"]
        raise ValueError(str(error.get("message") or error.get("code") or "Deriv identity authorization failed"))
    identity = response.get("authorize") or response.get("data") or {}
    return identity if isinstance(identity, dict) else {}


def fetch_deriv_identity(access_token: str) -> dict:
    """Fetch non-secret identity attributes exposed by Deriv OAuth authorization."""
    return asyncio.run(_authorize_deriv_identity_async(access_token))


def _safe_deriv_identity(identity: dict | None) -> dict:
    """Persist only provider identity attributes; never store OAuth tokens here."""
    if not isinstance(identity, dict):
        return {}
    allowed = {
        "user_id", "loginid", "email", "fullname", "first_name", "last_name",
        "username", "country", "residence", "preferred_language", "language",
        "timezone", "phone", "phone_number", "country_code", "avatar_url",
    }
    return {
        key: value
        for key, value in identity.items()
        if key in allowed and value not in (None, "", [])
        and isinstance(value, (str, int, float, bool))
    }


def sync_deriv_user_identity(user, identity: dict | None, profile=None):
    """Project Deriv identity fields into AlgoBot's user/profile without replacing secrets."""
    safe = _safe_deriv_identity(identity)
    if not safe:
        return {}

    changed = []
    email = str(safe.get("email") or "").strip()
    if email:
        user.email = email
        changed.append("email")

    first_name = str(safe.get("first_name") or "").strip()
    last_name = str(safe.get("last_name") or "").strip()
    fullname = str(safe.get("fullname") or "").strip()
    if fullname and (not first_name or not last_name):
        parts = fullname.split()
        first_name = first_name or parts[0]
        last_name = last_name or (" ".join(parts[1:]) if len(parts) > 1 else "")
    if first_name:
        user.first_name = first_name
        changed.append("first_name")
    if last_name:
        user.last_name = last_name
        changed.append("last_name")
    if changed:
        user.save(update_fields=sorted(set(changed)))

    if profile is not None:
        profile_changed = []
        country = str(safe.get("country") or safe.get("residence") or "").strip()
        avatar_url = str(safe.get("avatar_url") or "").strip()
        if country:
            profile.country = country
            profile_changed.append("country")
        if avatar_url:
            profile.avatar_url = avatar_url
            profile_changed.append("avatar_url")
        if profile_changed:
            profile.save(update_fields=sorted(set(profile_changed) | {"updated_at"}))

    return safe


def _persist_deriv_account(*, user, broker, record, access_token, refresh_token, expires_at, websocket_balance=None, websocket_health="not_checked", deriv_identity=None):
    """Persist one Deriv account returned by OAuth without preferred-account state."""
    account_id = _account_id(record)
    if not account_id:
        return None
    websocket_balance = websocket_balance or {}
    currency = record.get("currency") or websocket_balance.get("currency") or "USD"
    balance_value = record.get("balance") if record.get("balance") is not None else websocket_balance.get("balance") or 0
    equity_value = websocket_balance.get("equity") if websocket_balance.get("equity") is not None else 0
    avatar_url = str(record.get("avatar_url") or websocket_balance.get("avatar_url") or "").strip()
    account_type = _account_type(record, websocket_balance)

    broker_account, _ = BrokerAccount.objects.get_or_create(broker=broker, account_id=account_id, defaults={"user": user})
    broker_account.user = user
    broker_account.currency = currency
    broker_account.balance = balance_value
    broker_account.equity = equity_value
    broker_account.status = "active"
    broker_account.credentials = {
        **(broker_account.credentials or {}),
        "account_type": account_type,
        "connection_health": websocket_health,
        **({"avatar_url": avatar_url} if avatar_url else {}),
        **({"deriv_identity": _safe_deriv_identity(deriv_identity)} if deriv_identity else {}),
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
        defaults={"broker": broker, "status": "connected" if websocket_health == "verified" else "degraded", "last_ping": timezone.now() if websocket_health == "verified" else None, "connected_at": timezone.now(), "heartbeat": {"oauth_verified": True, "websocket_health": websocket_health}},
    )
    return broker_account
