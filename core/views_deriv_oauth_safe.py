"""Fast, non-looping Deriv OAuth callback for the browser connection flow."""
import logging
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.shortcuts import redirect
from core.auth_redirects import first_safe_auth_destination
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
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
    return redirect("broker_marketplace_page" if authenticated else "login_page")


def callback(request):
    # Deriv OAuth connects a broker to an existing verified AlgoBot account; it
    # is not a substitute for local registration, email verification, or login.
    if not request.user.is_authenticated:
        return _fail(
            request,
            "Sign in to your verified AlgoBot account before connecting Deriv. Broker authorization cannot create or sign in to an AlgoBot account.",
            "deriv_oauth_requires_local_account",
        )
    from core.broker_onboarding import has_verified_account_email
    if not has_verified_account_email(request.user):
        DerivOAuthService.clear_oauth_session(request)
        messages.info(request, "Verify your AlgoBot email before connecting Deriv.")
        return redirect("verify_email_page")
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
        # Include only the exception class / fixed diagnostic code in the
        # message because the structured formatter intentionally omits extras.
        # Never include OAuth access tokens or provider response payloads.
        logger.warning(
            "deriv_oauth_websocket_verification_unavailable error_type=%s",
            websocket_verification_error,
        )
    identity_loginid = str(
        deriv_identity.get("loginid") or deriv_identity.get("account_id") or ""
    ).strip()
    if identity_loginid and identity_loginid != selected_account_id:
        websocket_verification_error = "identity_mismatch"
    elif not identity_loginid and not websocket_verification_error:
        websocket_verification_error = "identity_missing"

    # The OAuth authorize response describes the token's default identity and
    # is not authoritative for every account returned by the account-list API.
    # In particular, a user may have both VRTC (demo) and CR (real) accounts.
    # Do not reject the entire OAuth link because this optional identity probe
    # reports another login ID; validate the selected account with its own OTP
    # session through the canonical adapter below.
    broker, _ = Broker.objects.get_or_create(broker_type="deriv", defaults={"name":"Deriv","status":"active","supports_live":True,"websocket_endpoint":settings.DERIV_AUTH_WS_BASE_URL})
    # Deriv's provider-issued user_id is a stable ownership signal across a
    # user's DEMO/REAL login IDs. It may confirm that an existing account is
    # already owned by this local user, but never authenticates a local user.
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
    user = request.user
    existing_selected = BrokerAccount.objects.filter(
        broker=broker, account_id=selected_account_id
    ).select_related("user").first()
    if existing_selected and existing_selected.user_id != user.id:
        return _fail(
            request,
            "That Deriv account is already connected to another AlgoBot user. Your dashboard was not opened.",
            "deriv_oauth_account_ownership_conflict",
        )
    if identity_account and identity_account.user_id != user.id:
        return _fail(
            request,
            "This Deriv identity is already linked to another AlgoBot user. Your dashboard was not opened.",
            "deriv_oauth_identity_ownership_conflict",
        )
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
        # Initially mark only the selected account as verified when the optional
        # identity probe matches. The account-scoped adapter check below is the
        # authoritative validation and can promote a valid demo or real account.
        identity_loginid = str(deriv_identity.get("loginid") or deriv_identity.get("account_id") or "").strip()
        websocket_health = (
            "verified"
            if current_id == selected_account_id and identity_loginid == selected_account_id
            else "not_checked"
        )
        try:
            persisted = _persist_deriv_account(
                user=user, broker=broker, record=record,
                access_token=access_token, refresh_token=refresh_token,
                expires_at=expires_at, websocket_balance={},
                websocket_health=websocket_health, deriv_identity=deriv_identity,
            )
        except Exception as exc:
            logger.error(
                "deriv_oauth_account_persistence_failed",
                extra={"error_type": exc.__class__.__name__, "account_id": current_id},
            )
            return _fail(
                request,
                "AlgoBot could not securely save the broker connection. Check the deployment's credential-encryption configuration and retry from Broker Management.",
                "deriv_oauth_account_persistence_failed",
                error_type=exc.__class__.__name__,
            )
        if current_id == selected_account_id and persisted is None:
            # The globally unique broker/account key may have been claimed by
            # another user between the preflight ownership check and this write.
            # Fail closed rather than dereferencing None or transferring ownership.
            return _fail(
                request,
                "That Deriv account could not be attached to this AlgoBot user. Refresh Broker Management and retry.",
                "deriv_oauth_selected_account_unavailable",
            )
        if persisted:
            persisted_ids.append(current_id)
            if current_id == selected_account_id:
                selected_broker_account = persisted
    if selected_broker_account is None:
        return _fail(request, "Deriv authorization succeeded, but AlgoBot could not persist the selected trading account. Your dashboard was not opened.", "deriv_oauth_selected_account_not_persisted")
    # Establish and persist the canonical broker connection only after the provider
    # identity check succeeded. OAuth token exchange by itself is not enough to
    # unlock the dashboard or report the broker as connected.
    try:
        from asgiref.sync import async_to_sync
        from apps.brokers.services import BrokerConnectionService
        # Always validate the selected account via its account-scoped OTP
        # session, regardless of the optional global authorize identity probe.
        # This supports users whose OAuth grants include both demo and real IDs.
        async_to_sync(BrokerConnectionService().connect)(broker, selected_broker_account)
        selected_broker_account.refresh_from_db()
        websocket_verification_error = None
    except Exception as exc:
        websocket_verification_error = exc.__class__.__name__
        BrokerConnection.objects.filter(broker_account=selected_broker_account).update(
            status="degraded",
            last_ping=None,
            heartbeat={
                "oauth_verified": True,
                "connection_validation": "failed",
                "error_type": websocket_verification_error,
            },
        )
        selected_broker_account.refresh_from_db()
        logger.warning(
            "deriv_oauth_connection_validation_failed",
            extra={"error": websocket_verification_error},
        )

    if selected_broker_account is None:
        return _fail(
            request,
            "AlgoBot could not securely persist the selected Deriv account. No dashboard access was granted.",
            "deriv_oauth_selected_account_unavailable",
        )
    if selected_broker_account.is_connection_eligible:
        select_account(request, selected_broker_account)
    DerivOAuthService.clear_oauth_session(request)
    logger.info("deriv_oauth_authorized_account_persisted", extra={"account_id":selected_account_id,"account_count":len(persisted_ids)})
    if websocket_verification_error:
        messages.warning(
            request,
            f"Deriv account {selected_account_id} was saved, but its broker connection could not be verified. "
            "Demo/real account data and trading remain unavailable until Broker Management completes a successful connection check.",
        )
    else:
        messages.success(
            request,
            f"Deriv account {selected_account_id} was authorized and its WebSocket identity verified. "
            "Refresh the dashboard to load the latest broker snapshot.",
        )
    if selected_broker_account.is_connection_eligible:
        # Do not send a newly onboarded user straight into the workspace until
        # the minimum AlgoBot profile identity fields have been completed.
        request.user.refresh_from_db(fields=["first_name", "last_name"])
        if not request.user.first_name.strip() or not request.user.last_name.strip():
            return redirect("profile_completion_page")
        requested = first_safe_auth_destination(
            request, request.session.pop("broker_onboarding_next", "")
        )
        if requested and not requested.startswith(("/brokers/", "/auth/google/", "/login/", "/register/")):
            return redirect(requested)
        return redirect("dashboard_page")
    return redirect("broker_marketplace_page")
