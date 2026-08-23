"""Strict broker OAuth callback used by the browser connection flow.

The callback never invents a broker account. A successful OAuth exchange must be
followed by a real Deriv authorization response so the local session is tied to
the broker identity that actually authenticated.
"""

import asyncio
import json
import logging

import websockets
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect

from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService
from trading.models import DerivAccount

logger = logging.getLogger("oauth")


async def _authorize(access_token: str) -> dict:
    """Authorize the freshly issued token and return the broker account payload."""
    endpoint = "wss://ws.derivws.com/websockets/v3"
    async with websockets.connect(endpoint, open_timeout=10, close_timeout=10) as ws:
        await ws.send(json.dumps({"authorize": access_token}))
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    if response.get("error"):
        raise ValueError(response["error"].get("message", "Deriv authorization failed"))
    return response.get("authorize") or {}


def _ensure_defaults(user):
    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)


def callback(request):
    """Complete Deriv OAuth without creating synthetic/fallback users."""
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
    valid, reason = DerivOAuthService.validate_pkce(
        code_verifier, redirect_uri, request.build_absolute_uri("/callback/").split("?", 1)[0]
        if False else __import__("django.conf").conf.settings.DERIV_REDIRECT_URI
    )
    if not valid or not code:
        logger.warning("deriv_oauth_pkce_or_code_validation_failed", extra={"error": reason})
        messages.error(request, "The broker connection could not be validated. Please try again.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(
        code, code_verifier, http_client=__import__("requests")
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
        account = asyncio.run(_authorize(access_token))
    except Exception as exc:
        logger.exception("deriv_oauth_authorize_failed", extra={"error": str(exc)})
        messages.error(request, "Deriv authentication succeeded, but AlgoBot could not verify the broker account.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    account_id = account.get("loginid") or account.get("account_id")
    if not account_id:
        logger.error("deriv_oauth_missing_account_identity")
        messages.error(request, "Deriv did not provide a broker account identity. No local user was created.")
        DerivOAuthService.clear_oauth_session(request)
        return redirect("broker_connect_page")

    # Never attach a broker identity to a different local user.
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
        # Deriv OAuth is the product's identity provider. This is a broker-backed
        # shadow identity, not a generated/fake account: it is created only after
        # Deriv returns a verified account id and the token has been authorized.
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
    deriv_account.account_type = "demo" if account.get("is_virtual") else "real"
    deriv_account.currency = account.get("currency") or ""
    deriv_account.save()

    DerivOAuthService.clear_oauth_session(request)
    messages.success(request, f"Deriv account {account_id} connected successfully.")
    return redirect("dashboard_page")
