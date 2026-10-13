"""Fast, non-looping Deriv OAuth callback for the browser connection flow."""
import logging
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect
from apps.brokers.models import Broker, BrokerAccount
from core.account_context import select_account
from core.models import BotSettings, Subscription, UserProfile
from core.services.oauth_service import DerivOAuthService
from core.views_broker_oauth import _account_id, _persist_deriv_account, _verify_account, fetch_deriv_identity, sync_deriv_user_identity

logger = logging.getLogger("oauth")


def _ensure_defaults(user):
    UserProfile.objects.get_or_create(user=user)
    Subscription.objects.get_or_create(user=user)
    BotSettings.objects.get_or_create(user=user)


def _connection_destination(request):
    return "broker_marketplace_page" if request.user.is_authenticated else "broker_connect_page"


def _fail(request, message, event, **extra):
    logger.warning(event, extra=extra)
    # Resolve request.user before clearing OAuth/session state: Django's
    # request.user is lazy, and clearing the session first can make an
    # authenticated callback look anonymous and send it to the wrong page.
    authenticated = bool(request.user.is_authenticated)
    DerivOAuthService.clear_oauth_session(request)
    messages.error(request, message)
    return redirect("broker_marketplace_page" if authenticated else "broker_connect_page")


def callback(request):
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
    initiating_user_id = request.session.get("oauth_initiating_user_id")
    if initiating_user_id is not None:
        callback_user_id = str(request.user.pk) if request.user.is_authenticated else "__anonymous__"
        if str(initiating_user_id) != callback_user_id:
            return _fail(
                request,
                "Your browser session changed during broker authorization. Start a new connection from Broker Management.",
                "deriv_oauth_session_user_mismatch",
                error={"initiating_user_id": initiating_user_id, "callback_user_id": callback_user_id},
            )
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
    deriv_identity = {}
    websocket_verification_error = None
    try:
        # This helper performs a real Deriv WebSocket authorize request. A REST
        # account-list response alone is not evidence of a live authorized session.
        deriv_identity = fetch_deriv_identity(access_token)
        identity_loginid = str(
            deriv_identity.get("loginid") or deriv_identity.get("account_id") or ""
        ).strip()
        if not identity_loginid:
            websocket_verification_error = "identity_missing"
        elif identity_loginid != selected_account_id:
            websocket_verification_error = "identity_mismatch"
    except Exception as exc:
        websocket_verification_error = exc.__class__.__name__
        logger.warning(
            "deriv_oauth_websocket_verification_unavailable",
            extra={"error": websocket_verification_error},
        )
    identity_loginid = str(
        deriv_identity.get("loginid") or deriv_identity.get("account_id") or ""
    ).strip()
    if identity_loginid and identity_loginid != selected_account_id:
        websocket_verification_error = "identity_mismatch"
    elif not identity_loginid and not websocket_verification_error:
        websocket_verification_error = "identity_missing"

    # An anonymous OAuth callback is an account sign-in, not merely a broker
    # connection. Require a live, matching provider identity before creating or
    # reusing a local user; REST account-list data alone cannot authenticate a
    # person into an existing AlgoBot account.
    if websocket_verification_error == "identity_mismatch":
        return _fail(
            request,
            "Deriv verified a different account identity. No AlgoBot account was signed in or changed; retry from the correct broker account.",
            "deriv_oauth_identity_mismatch",
        )
    if not request.user.is_authenticated and (
        websocket_verification_error
        or not identity_loginid
        or deriv_identity.get("user_id") in (None, "")
    ):
        return _fail(
            request,
            "AlgoBot could not securely verify your Deriv identity. No account was signed in or linked. Please retry, or sign in to AlgoBot first and connect Deriv from Broker Management.",
            "deriv_oauth_anonymous_identity_unverified",
            error=websocket_verification_error or "identity_fields_missing",
        )

    broker, _ = Broker.objects.get_or_create(broker_type="deriv", defaults={"name":"Deriv","status":"active","supports_live":True,"websocket_endpoint":settings.DERIV_AUTH_WS_BASE_URL})
    # Deriv's provider-issued user_id is the stable identity across that user's
    # authorized DEMO/REAL login IDs. Reuse the owning AlgoBot user when that
    # identity was previously verified, rather than creating one user per account.
    identity_user_id = deriv_identity.get("user_id")
    identity_account = None
    if identity_user_id not in (None, ""):
        identity_account = (
            BrokerAccount.objects.filter(
                broker=broker,
                credentials__deriv_identity__user_id=identity_user_id,
            )
            .select_related("user")
            .order_by("id")
            .first()
        )
    if request.user.is_authenticated:
        user = request.user
        existing_selected = BrokerAccount.objects.filter(broker=broker, account_id=selected_account_id).select_related("user").first()
        if existing_selected and existing_selected.user_id != user.id:
            return _fail(request, "That Deriv account is already connected to another AlgoBot user. Your dashboard was not opened.", "deriv_oauth_account_ownership_conflict")
        if identity_account and identity_account.user_id != user.id:
            return _fail(request, "This Deriv identity is already linked to another AlgoBot user. Your dashboard was not opened.", "deriv_oauth_identity_ownership_conflict")
    else:
        existing_selected = BrokerAccount.objects.filter(broker=broker, account_id=selected_account_id).select_related("user").first()
        if existing_selected and identity_account and existing_selected.user_id != identity_account.user_id:
            return _fail(request, "Deriv account ownership does not match the previously verified provider identity. Your dashboard was not opened.", "deriv_oauth_identity_account_conflict")
        if existing_selected:
            # Never turn knowledge of a broker login ID into local account
            # authentication. Reuse an existing AlgoBot identity only when the
            # verified stable Deriv user ID already maps to that same owner.
            if not identity_account or identity_account.user_id != existing_selected.user_id:
                return _fail(
                    request,
                    "This Deriv account is already linked. Sign in to the existing AlgoBot account before reconnecting it.",
                    "deriv_oauth_existing_account_requires_local_auth",
                )
            user = existing_selected.user
        elif identity_account:
            user = identity_account.user
        else:
            user = User.objects.create(username=f"deriv_{selected_account_id}", first_name="Deriv")
            user.set_unusable_password()
            user.save(update_fields=["password"])
    # Explicitly bind the OAuth user to Django's browser session backend.
    # This prevents the post-OAuth session from becoming anonymous and causing
    # the broker API to return an authentication-credentials error.
    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.save()
    _ensure_defaults(user)
    profile = UserProfile.objects.get(user=user)
    sync_deriv_user_identity(user, deriv_identity, profile=profile)
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
        # Only mark the selected account connected when the OAuth token was also
        # successfully authorized over Deriv WebSocket and the provider identity
        # matches that exact account. OAuth REST verification alone is not a live
        # WebSocket/session health check, so all other accounts remain degraded.
        identity_loginid = str(deriv_identity.get("loginid") or deriv_identity.get("account_id") or "").strip()
        websocket_health = (
            "verified"
            if current_id == selected_account_id and identity_loginid == selected_account_id
            else "not_checked"
        )
        persisted = _persist_deriv_account(user=user, broker=broker, record=record, access_token=access_token, refresh_token=refresh_token, expires_at=expires_at, websocket_balance={}, websocket_health=websocket_health, deriv_identity=deriv_identity)
        if persisted:
            persisted_ids.append(current_id)
            if current_id == selected_account_id:
                selected_broker_account = persisted
    if selected_broker_account is None:
        return _fail(request, "Deriv authorization succeeded, but AlgoBot could not persist the selected trading account. Your dashboard was not opened.", "deriv_oauth_selected_account_not_persisted")
    if selected_broker_account.is_connection_eligible:
        select_account(request, selected_broker_account)
    DerivOAuthService.clear_oauth_session(request)
    logger.info("deriv_oauth_authorized_account_persisted", extra={"account_id":selected_account_id,"account_count":len(persisted_ids)})
    if websocket_verification_error:
        messages.warning(
            request,
            f"Deriv account {selected_account_id} was saved, but its live connection could not be verified. "
            "Balance, equity, and trading remain unavailable until Broker Management completes a successful connection check.",
        )
    else:
        messages.success(
            request,
            f"Deriv account {selected_account_id} was authorized and its WebSocket identity verified. "
            "Refresh the dashboard to load the latest broker snapshot.",
        )
    return redirect("broker_marketplace_page")
