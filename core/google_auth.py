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
    request.session[_STATE_KEY] = state
    request.session[_STARTED_KEY] = int(timezone.now().timestamp())
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + params)


@require_GET
def google_login_callback(request):
    expected = request.session.pop(_STATE_KEY, None)
    started = request.session.pop(_STARTED_KEY, None)
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
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"code": code, "client_id": client_id, "client_secret": client_secret,
                  "redirect_uri": _redirect_uri(), "grant_type": "authorization_code"},
            timeout=10,
        )
        response.raise_for_status()
        token = str(response.json().get("access_token") or "")
        if not token:
            raise ValueError("Missing access token")
        profile_response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": "Bearer " + token}, timeout=10,
        )
        profile_response.raise_for_status()
        identity = profile_response.json()
    except (requests.RequestException, ValueError, TypeError):
        logger.warning("google_login_exchange_failed")
        messages.error(request, "Google sign-in could not be completed. Please try again.")
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
