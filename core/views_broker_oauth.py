"""Strict broker OAuth callback used by the browser connection flow."""

import asyncio
import json
import logging

import requests
import websockets
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect

from apps.brokers.models import Broker, BrokerAccount
from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService
from trading.models import DerivAccount

logger = logging.getLogger("oauth")

DERIV_API_BASE = "https://api.derivws.com"
DERIV_ACCOUNTS_URL = f"{DERIV_API_BASE}/trading/v1/options/accounts"


def _account_records(payload: dict) -> list[dict]:
    """Normalize the current Deriv Options accounts response."""
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _select_account(payload: dict) -> dict | None:
    accounts = _account_records(payload)
    return accounts[0] if accounts else None


async def _verify_authenticated_websocket(access_token: str, account_id: str) -> dict:
    """Verify the OAuth token and authenticated WebSocket using Deriv's current API.

    Deriv's current API no longer accepts a raw OAuth token in the legacy
    ``wss://ws.derivws.com/websockets/v3`` handshake.  The token must first be
    used with the Options REST API to obtain a short-lived, one-time WebSocket
    URL (OTP).  The returned URL is then connected to directly.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Deriv-App-ID": settings.DERIV_APP_ID,
        "Accept": "application/json",
    }
    try:
        otp_response = requests.post(
            f"{DERIV_ACCOUNTS_URL}/{account_id}/otp",
            headers=headers,
            timeout=(3.05, 10),
        )
        otp_response.raise_for_status()
        otp_payload = otp_response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 401:
            raise ValueError("Deriv rejected the OAuth credential while creating the authenticated WebSocket session") from exc
        if status == 403:
            raise ValueError("Deriv denied trading access for this OAuth credential") from exc
        raise ValueError("Deriv could not create an authenticated WebSocket session") from exc
    except (requests.RequestException, ValueError) as exc:
        raise ValueError("Deriv authentication service is temporarily unavailable") from exc

    ws_url = (otp_payload.get("data") or {}).get("url")
    if not ws_url:
        raise ValueError("Deriv did not return an authenticated WebSocket URL")

    async with websockets.connect(ws_url, open_timeout=10, close_timeout=10) as ws:
        # The OTP authenticates the connection.  A balance request is a small,
        # account-scoped smoke test that proves the session is usable.
        await ws.send(json.dumps({"balance": 1, "req_id": 1}))
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

    if response.get("error"):
        raise ValueError(response["error"].get("message", "Deriv authenticated WebSocket verification failed"))
    return response.get("balance") or {}


def _verify_account(access_token: str) -> tuple[dict | None, list[dict]]:
    """Resolve a real Deriv Options account through the authenticated REST API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Deriv-App-ID": settings.DERIV_APP_ID,
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            DERIV_ACCOUNTS_URL,
            headers=headers,
            timeout=(3.05, 10),
        )
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
    account = _select_account(payload)
    return account, accounts


def _ensure_defaults(user):
    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)


def callback(request):
    """Complete Deriv OAuth without synthetic/fallback broker identities."""
    error = request.GET.get("error")
    if error:
        messages.error(request, "Deriv sign-in was cancelled or rejected. Please try again.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    received_state = request.GET.get("state")
    code = request.GET.get("code")
    expected_state = request.session.get("oauth_state")
    valid, reason = DerivOAuthService.validate_state(received_state, expected_state)
    if not valid:
        logger.warning("deriv_oauth_state_validation_failed", extra={"error": reason})
        messages.error(request, "Broker security validation failed. Please restart the connection.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    code_verifier = request.session.get("pkce_verifier")
    redirect_uri = request.session.get("oauth_redirect_uri")
    valid, reason = DerivOAuthService.validate_pkce(code_verifier, redirect_uri, settings.DERIV_REDIRECT_URI)
    if not valid or not code:
        logger.warning("deriv_oauth_pkce_or_code_validation_failed", extra={"error": reason})
        messages.error(request, "The broker connection could not be validated. Please try again.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(
        code, code_verifier, http_client=requests
    )
    if not success or not token_data:
        logger.error("deriv_oauth_token_exchange_failed", extra={"error": token_error})
        messages.error(request, "Deriv could not complete the secure connection. Please try again.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    valid, reason = DerivOAuthService.validate_token_response(token_data)
    if not valid:
        logger.error("deriv_oauth_invalid_token_response", extra={"error": reason})
        messages.error(request, "Deriv returned an invalid authorization response.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    access_token = token_data["access_token"]
    try:
        account, accounts = _verify_account(access_token)
        if not account:
            raise ValueError("Deriv returned no Options trading account for this user")
        account_id = account.get("account_id") or account.get("loginid")
        if not account_id:
            raise ValueError("Deriv did not return a broker account identity")

        # Prove that the same credential can establish an authenticated
        # real-time trading session before persisting it locally.
        balance = asyncio.run(_verify_authenticated_websocket(access_token, account_id))
    except Exception as exc:
        logger.exception("deriv_oauth_broker_verification_failed", extra={"error": str(exc)})
        messages.error(request, "Deriv authentication succeeded, but AlgoBot could not verify the trading connection.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    existing_account = DerivAccount.objects.filter(account_id=account_id).select_related("user").first()
    if request.user.is_authenticated:
        user = request.user
        if existing_account and existing_account.user_id != user.id:
            logger.error("deriv_account_already_linked", extra={"account_id": account_id})
            messages.error(request, "That Deriv account is already connected to another AlgoBot user.")
            DerivOAuthService.clear_oauth_session(request)
            return redirect("broker_connect_page")
    elif existing_account:
        user = existing_account.user
    else:
        # This local identity is created only after Deriv has authenticated the
        # user, returned a real account id, and passed an authenticated
        # WebSocket smoke test. There is no random/synthetic fallback identity.
        username = f"deriv_{account_id}"
        user = User.objects.create(username=username, first_name="Deriv")
        user.set_unusable_password()
        user.save(update_fields=["password"])
        logger.info("deriv_oauth_broker_identity_created", extra={"user_id": user.id, "account_id": account_id})

    auth_login(request, user)
    _ensure_defaults(user)

    expires_in = int(token_data.get("expires_in", 3600))
    deriv_account, _ = DerivAccount.objects.get_or_create(user=user)
    deriv_account.account_id = account_id
    deriv_account.set_access_token(access_token)
    deriv_account.set_refresh_token(token_data.get("refresh_token"))
    deriv_account.expires_at = DerivOAuthService.parse_token_expiry(expires_in)
    deriv_account.token_status = "active"
    deriv_account.account_type = account.get("account_type") or "demo"
    deriv_account.currency = account.get("currency") or balance.get("currency") or "USD"
    deriv_account.save()

    broker, _ = Broker.objects.get_or_create(
        broker_type="deriv",
        defaults={
            "name": "Deriv",
            "status": "active",
            "supports_live": True,
            "websocket_endpoint": "wss://api.derivws.com/trading/v1/options/ws/",
        },
    )
    BrokerAccount.objects.update_or_create(
        broker=broker,
        account_id=account_id,
        defaults={
            "user": user,
            "currency": account.get("currency") or balance.get("currency") or "USD",
            "status": "active",
            "is_preferred": True,
            "credentials": {"account_type": account.get("account_type") or "demo"},
        },
    )

    DerivOAuthService.clear_oauth_session(request)
    messages.success(request, f"Deriv account {account_id} connected successfully.")
    return redirect("dashboard_page")
