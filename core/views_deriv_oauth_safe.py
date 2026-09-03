"""Fast, non-looping Deriv OAuth callback for the browser connection flow.

The callback is limited to OAuth/token/account persistence. Live broker
activation is performed by the authenticated broker workspace after OAuth.
OAuth failures never send the user to the dashboard: the connection workflow
remains in the broker workspace so the user can see the error and retry.
"""
import logging
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect
from apps.brokers.models import Broker, BrokerAccount
from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService
from core.views_broker_oauth import _account_id, _persist_deriv_account, _verify_account

logger = logging.getLogger("oauth")


def _ensure_defaults(user):
    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)


def _connection_destination(request):
    """Return the broker workspace, never the dashboard, after OAuth failure."""
    return "broker_marketplace_page" if request.user.is_authenticated else "broker_connect_page"


def _fail(request, message, event, **extra):
    """Terminate the OAuth attempt without restarting OAuth or opening dashboard."""
    logger.warning(event, extra=extra)
    DerivOAuthService.clear_oauth_session(request)
    messages.error(request, message)
    return redirect(_connection_destination(request))


def callback(request):
    """Complete OAuth and return to broker management, not the dashboard."""
    if request.GET.get("error"):
        return _fail(request, "Deriv sign-in was cancelled or rejected. You are still in Broker Management; start a new connection when ready.", "deriv_oauth_provider_error")

    received_state = request.GET.get("state")
    code = request.GET.get("code")
    valid, reason = DerivOAuthService.validate_state(received_state, request.session.get("oauth_state"))
    if not valid:
        return _fail(request, "Broker security validation failed. Your dashboard was not opened. Start a new connection from Broker Management.", "deriv_oauth_state_validation_failed", error=reason)

    code_verifier = request.session.get("pkce_verifier")
    redirect_uri = request.session.get("oauth_redirect_uri")
    valid, reason = DerivOAuthService.validate_pkce(code_verifier, redirect_uri, settings.DERIV_REDIRECT_URI)
    if not valid or not code:
        return _fail(request, "The broker authorization could not be validated. Your dashboard was not opened. Start a new connection from Broker Management.", "deriv_oauth_pkce_or_code_validation_failed", error=reason)

    success, token_data, token_error = DerivOAuthService.exchange_code_for_token(code, code_verifier, http_client=requests)
    if not success or not token_data:
        return _fail(request, "Deriv could not complete the secure connection. Your dashboard was not opened; retry from Broker Management.", "deriv_oauth_token_exchange_failed", error=token_error)

    valid, reason = DerivOAuthService.validate_token_response(token_data)
    if not valid:
        return _fail(request, "Deriv returned an invalid authorization response. Your dashboard was not opened; retry from Broker Management.", "deriv_oauth_invalid_token_response", error=reason)

    access_token = token_data["access_token"]
    try:
        selected, accounts = _verify_account(access_token)
        if not selected or not accounts:
            raise ValueError("Deriv returned no trading account")
        selected_account_id = _account_id(selected)
        if not selected_account_id:
            raise ValueError("Deriv did not return a trading account identity")
    except Exception as exc:
        logger.exception("deriv_oauth_broker_account_verification_failed")
        return _fail(request, "Deriv authorization succeeded, but AlgoBot could not verify the trading account. Your dashboard was not opened; retry from Broker Management.", "deriv_oauth_broker_account_verification_failed", error=exc.__class__.__name__)

    broker, _ = Broker.objects.get_or_create(
        broker_type="deriv",
        defaults={"name":"Deriv","status":"active","supports_live":True,"websocket_endpoint":settings.DERIV_AUTH_WS_BASE_URL},
    )

    if request.user.is_authenticated:
        user = request.user
        existing_selected = BrokerAccount.objects.filter(broker=broker, account_id=selected_account_id).select_related("user").first()
        if existing_selected and existing_selected.user_id != user.id:
            return _fail(request, "That Deriv account is already connected to another AlgoBot user. Your dashboard was not opened.", "deriv_oauth_account_ownership_conflict")
    else:
        existing_selected = BrokerAccount.objects.filter(broker=broker, account_id=selected_account_id).select_related("user").first()
        if existing_selected:
            user = existing_selected.user
        else:
            user = User.objects.create(username=f"deriv_{selected_account_id}", first_name="Deriv")
            user.set_unusable_password()
            user.save(update_fields=["password"])

    auth_login(request, user)
    _ensure_defaults(user)
    expires_in = int(token_data.get("expires_in", 3600))
    expires_at = DerivOAuthService.parse_token_expiry(expires_in)
    refresh_token = token_data.get("refresh_token", "")

    persisted_ids = []
    selected_broker_account = None
    for record in accounts:
        current_id = _account_id(record)
        if not current_id:
            continue
        existing = BrokerAccount.objects.filter(broker=broker, account_id=current_id).select_related("user").first()
        if existing and existing.user_id != user.id:
            if current_id == selected_account_id:
                return _fail(request, "That Deriv account is already connected to another AlgoBot user. Your dashboard was not opened.", "deriv_oauth_account_ownership_conflict")
            continue
        persisted = _persist_deriv_account(
            user=user, broker=broker, record=record, access_token=access_token,
            refresh_token=refresh_token, expires_at=expires_at,
            preferred=(current_id == selected_account_id), websocket_balance={}, websocket_health="not_checked",
        )
        if persisted:
            persisted_ids.append(current_id)
            if current_id == selected_account_id:
                selected_broker_account = persisted

    if persisted_ids:
        BrokerAccount.objects.filter(user=user, broker=broker).exclude(account_id=selected_account_id).update(is_preferred=False)

    if selected_broker_account is None:
        return _fail(request, "Deriv authorization succeeded, but AlgoBot could not persist the selected trading account. Your dashboard was not opened.", "deriv_oauth_selected_account_not_persisted")

    DerivOAuthService.clear_oauth_session(request)
    logger.info("deriv_oauth_authorized_account_persisted", extra={"account_id":selected_account_id,"account_count":len(persisted_ids)})
    messages.success(request, f"Deriv account {selected_account_id} authorized. Broker connection verification is now available in Broker Management.")
    return redirect("broker_marketplace_page")
