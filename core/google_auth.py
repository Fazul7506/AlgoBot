"""Google OpenID Connect login for AlgoBot browser sessions.

This flow is distinct from the Gmail notification-channel OAuth flow.
"""
import base64
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
from core.auth_redirects import safe_auth_destination
from django.views.decorators.http import require_GET

from core.models import BotSettings, GoogleIdentity, Subscription, UserProfile

logger = logging.getLogger("account_auth")
from core.auth_rate_limit import allow_auth_attempt
_STATE_KEY = "algobot_google_login_state"
_STARTED_KEY = "algobot_google_login_started"
_NONCE_KEY = "algobot_google_login_nonce"
_VERIFIER_KEY = "algobot_google_login_pkce_verifier"
_LINK_USER_KEY = "algobot_google_link_user_id"


def _redirect_uri():
    """Return the explicit Google callback or derive it from Django canonical settings."""
    import os

    configured_uri = str(os.getenv("GOOGLE_LOGIN_REDIRECT_URI", "") or "").strip()
    if configured_uri:
        return configured_uri
    base_url = str(
        getattr(settings, "BASE_URL", "")
        or os.getenv("BASE_URL", "")
        or "http://127.0.0.1:8000"
    ).strip().rstrip("/")
    return f"{base_url}/auth/google/callback/"


@require_GET
def google_login_start(request):
    requested_next = safe_auth_destination(request, request.GET.get("next"))
    # Google authentication creates/signs into an AlgoBot identity only.
    # Broker authorization is a separate, explicit user action from the marketplace.
    if not requested_next:
        requested_next = "/dashboard/"
    if requested_next:
        request.session["broker_onboarding_next"] = requested_next
    if request.GET.get("intent") == "link":
        if not request.user.is_authenticated:
            messages.info(request, "Sign in to AlgoBot before linking Google.")
            return redirect("login_page")
        request.session[_LINK_USER_KEY] = str(request.user.pk)
    else:
        request.session.pop(_LINK_USER_KEY, None)
    if not allow_auth_attempt(request, "google-login-start", "", limit=15, window=900):
        messages.error(request, "Too many Google sign-in attempts. Please wait and try again.")
        return redirect("login_page")
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    if not client_id or not getattr(settings, "GOOGLE_CLIENT_SECRET", ""):
        messages.error(request, "Google sign-in is not configured on this deployment.")
        return redirect("login_page")
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
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
    link_user_id = request.session.pop(_LINK_USER_KEY, None)
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
    first_name = str(identity.get("given_name") or "").strip()
    last_name = str(identity.get("family_name") or "").strip()
    if not first_name or not last_name:
        display_name = str(identity.get("name") or "").strip()
        name_parts = display_name.split(None, 1)
        first_name = first_name or (name_parts[0] if name_parts else "")
        last_name = last_name or (name_parts[1] if len(name_parts) > 1 else "")
    if not subject or not email or identity.get("email_verified") is not True:
        messages.error(request, "Google did not provide a verified email identity.")
        return redirect("login_page")

    # Provider subject, not email or a derived username, is the durable identity key.
    # Track first-time creation separately from returning Google sign-in: these have
    # deliberately different post-authentication destinations.
    is_new_google_user = False
    request.session.pop("google_profile_completion_pending", None)
    request.session.pop("google_existing_login_dashboard", None)
    try:
        with transaction.atomic():
            google_identity = (
                GoogleIdentity.objects.select_for_update()
                .select_related("user")
                .filter(provider="google", subject=subject)
                .first()
            )

            if link_user_id:
                if not request.user.is_authenticated or str(request.user.pk) != str(link_user_id):
                    messages.error(request, "Your AlgoBot session changed during Google linking. Sign in and try again.")
                    return redirect("login_page")
                local_profile = UserProfile.objects.filter(user=request.user).first()
                if not local_profile or not local_profile.email_verified:
                    messages.error(request, "Verify your AlgoBot email before linking Google sign-in.")
                    return redirect("verify_email_page")
                if google_identity and google_identity.user_id != request.user.pk:
                    messages.error(request, "That Google identity is already linked to another AlgoBot account.")
                    return redirect("account_identity_page")
                if google_identity is None:
                    GoogleIdentity.objects.create(
                        user=request.user, provider="google", subject=subject, email=email
                    )
                else:
                    google_identity.email = email
                    google_identity.save(update_fields=["email", "updated_at"])
                messages.success(request, "Google sign-in is now linked to your AlgoBot account.")
                return redirect("account_identity_page")

            if google_identity:
                user = google_identity.user
                # Fill missing profile names from Google's verified OpenID profile;
                # do not overwrite names the user has already set locally.
                changed_fields = []
                if first_name and not user.first_name:
                    user.first_name = first_name
                    changed_fields.append("first_name")
                if last_name and not user.last_name:
                    user.last_name = last_name
                    changed_fields.append("last_name")
                if changed_fields:
                    user.save(update_fields=changed_fields)
                if not user.is_active:
                    messages.error(request, "This AlgoBot account is disabled. Contact support.")
                    return redirect("login_page")
                # This provider subject is already explicitly linked to this
                # local account, and Google has asserted email_verified=true.
                # Verify the local address only when it still matches the
                # provider's verified address; never silently change the email.
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if (
                    not profile.email_verified
                    and str(user.email or "").strip().lower() == email
                ):
                    profile.email_verified = True
                    profile.email_verified_at = timezone.now()
                    profile.save(update_fields=[
                        "email_verified", "email_verified_at", "updated_at"
                    ])
            else:
                if User.objects.filter(email__iexact=email).exists():
                    messages.info(
                        request,
                        "An AlgoBot account already uses this email. Sign in to that account first, then explicitly link Google from Account Identity.",
                    )
                    return redirect("login_page")

                username = "google_" + hashlib.sha256(subject.encode("utf-8")).hexdigest()[:32]
                if User.objects.filter(username=username).exists():
                    # A username collision is not proof of provider ownership.
                    messages.error(request, "Google identity could not be linked safely. Please contact support.")
                    return redirect("login_page")

                user = User.objects.create_user(
                    username=username, email=email, password=None,
                    first_name=first_name, last_name=last_name,
                )
                is_new_google_user = True
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.email_verified = True
                profile.email_verified_at = timezone.now()
                profile.save(update_fields=["email_verified", "email_verified_at", "updated_at"])
                Subscription.objects.get_or_create(user=user)
                BotSettings.objects.get_or_create(user=user)
                GoogleIdentity.objects.create(
                    user=user, provider="google", subject=subject, email=email
                )
    except IntegrityError:
        # Concurrent first-time callbacks may race on provider subject/email.
        # Re-resolve only by the verified subject; never fall back to email.
        google_identity = (
            GoogleIdentity.objects.select_related("user")
            .filter(provider="google", subject=subject)
            .first()
        )
        if google_identity and not link_user_id and google_identity.user.is_active:
            user = google_identity.user
        else:
            messages.error(request, "The Google identity could not be linked safely. Please try again.")
            return redirect("account_identity_page" if request.user.is_authenticated else "login_page")

    profile = UserProfile.objects.filter(user=user).first()
    if profile and profile.two_factor_enabled:
        # Do not establish an authenticated Django session until the second
        # factor succeeds, including for users signing in through Google.
        request.session["algobot_pending_2fa_user_id"] = user.pk
        request.session.pop("broker_onboarding_next", None)
        return redirect("two_factor_challenge_page")

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    UserProfile.objects.filter(user=user).update(last_login_at=timezone.now())
    # First-time Google signup must finish the local profile before broker setup.
    # A returning Google identity goes directly to the dashboard; never send an
    # existing user through signup/profile completion or broker marketplace again.
    request.session.pop("broker_onboarding_next", None)
    if is_new_google_user:
        request.session["google_profile_completion_pending"] = True
        return redirect("profile_completion_page")
    request.session["google_existing_login_dashboard"] = True
    return redirect("dashboard_page")
