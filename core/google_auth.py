"""Google OpenID Connect login for AlgoBot browser sessions.

This flow is distinct from the Gmail notification-channel OAuth flow.
"""
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import BotSettings, Subscription, UserProfile

logger = logging.getLogger("account_auth")
_STATE_KEY = "algobot_google_login_state"
_STARTED_KEY = "algobot_google_login_started"
_NONCE_KEY = "algobot_google_login_nonce"
_VERIFIER_KEY = "algobot_google_login_pkce_verifier"


def _redirect_uri():
    import os
    return os.getenv(
        "GOOGLE_LOGIN_REDIRECT_URI",
        f'{os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")}/auth/google/callback/',
    )


@require_GET
def google_login_start(request):
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    if not client_id or not getattr(settings, "GOOGLE_CLIENT_SECRET", ""):
        messages.error(request, "Google sign-in is not configured on this deployment.")
        return redirect("login_page")
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = __import__("base64").urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    request.session[_STATE_KEY] = state
    request.session[_STARTED_KEY] = int(timezone.now().timestamp())
    request.session[_NONCE_KEY] = nonce
    request.session[_VERIFIER_KEY] = code_verifier
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + params)


@require_GET
def google_login_callback(request):
    expected = request.session.pop(_STATE_KEY, None)
    started = request.session.pop(_STARTED_KEY, None)
    expected_nonce = request.session.pop(_NONCE_KEY, None)
    code_verifier = request.session.pop(_VERIFIER_KEY, None)
    received = str(request.GET.get("state") or "")
    if not expected or not received or not hmac.compare_digest(str(expected), received):
        messages.error(request, "Google sign-in could not be verified. Please try again.")
        return redirect("login_page")
    if not started or int(timezone.now().timestamp()) - int(started) > 600:
        messages.error(request, "Your Google sign-in request expired. Please try again.")
        return redirect("login_page")
    if request.GET.get("error"):
        messages.info(request, "Google sign-in was cancelled or declined.")
        return redirect("login_page")
    code = str(request.GET.get("code") or "")
    if not code:
        messages.error(request, "Google did not return an authorization code.")
        return redirect("login_page")
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        messages.error(request, "Google sign-in is not configured on this deployment.")
        return redirect("login_page")
    if not expected_nonce or not code_verifier:
        messages.error(request, "Google sign-in could not be verified. Please try again.")
        return redirect("login_page")
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
        response.raise_for_status()
        token_payload = response.json()
        raw_id_token = str(token_payload.get("id_token") or "")
        if not raw_id_token:
            raise ValueError("Missing OpenID Connect ID token")
        # google-auth verifies Google's signing key, issuer, audience, and expiry.
        # PKCE binds the code to this browser session; nonce binds the ID token
        # to this authentication request.
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token as google_id_token
        identity = google_id_token.verify_oauth2_token(
            raw_id_token, GoogleRequest(), audience=client_id
        )
    except Exception:
        logger.warning("google_login_exchange_or_id_token_validation_failed")
        messages.error(request, "Google sign-in could not be completed. Please try again.")
        return redirect("login_page")

    received_nonce = str(identity.get("nonce") or "")
    if not received_nonce or not hmac.compare_digest(expected_nonce, received_nonce):
        logger.warning("google_login_nonce_validation_failed")
        messages.error(request, "Google sign-in could not be verified. Please try again.")
        return redirect("login_page")

    subject = str(identity.get("sub") or "").strip()
    email = str(identity.get("email") or "").strip().lower()
    if not subject or not email or identity.get("email_verified") is not True:
        messages.error(request, "Google did not provide a verified email identity.")
        return redirect("login_page")

    # The stable Google subject is deterministically mapped to a local username.
    # An existing email is never silently linked to a Google identity.
    username = "google_" + hashlib.sha256(subject.encode("utf-8")).hexdigest()[:32]
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().filter(username=username).first()
            if user is None:
                if User.objects.filter(email__iexact=email).exists():
                    messages.info(request, "An account already uses this email. Sign in with that account; Google identity linking requires explicit authorization.")
                    return redirect("login_page")
                user = User.objects.create_user(username=username, email=email, password=None)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.email_verified = True
                profile.email_verified_at = timezone.now()
                profile.save(update_fields=["email_verified", "email_verified_at", "updated_at"])
                Subscription.objects.get_or_create(user=user)
                BotSettings.objects.get_or_create(user=user)
            else:
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if not profile.email_verified:
                    profile.email_verified = True
                    profile.email_verified_at = timezone.now()
                    profile.save(update_fields=["email_verified", "email_verified_at", "updated_at"])
    except IntegrityError:
        messages.error(request, "The Google account could not be linked safely. Please try again.")
        return redirect("login_page")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    UserProfile.objects.filter(user=user).update(last_login_at=timezone.now())
    from core.broker_onboarding import has_authorized_broker_connection
    if not has_authorized_broker_connection(user):
        return redirect("broker_marketplace_page")
    return redirect("dashboard_page")
