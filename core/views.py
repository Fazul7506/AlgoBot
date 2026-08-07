import secrets
import hashlib
import base64
import logging
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.contrib.auth.models import User

from trading.models import DerivAccount

oauth_logger = logging.getLogger("oauth")
DERIV_AUTHORIZE_URL = "https://auth.deriv.com/oauth2/auth"
DERIV_TOKEN_URL = "https://auth.deriv.com/oauth2/token"
OAUTH_TIMEOUT = (3.05, 10)


def home(request):
    return render(request, 'core/home.html')


def login_page(request):
    return render(request, 'core/login.html')


def register_page(request):
    return render(request, 'core/register.html')


def dashboard_page(request):
    return render(request, 'core/dashboard.html')


def markets_page(request):
    return render(request, 'core/markets.html')


def strategies_page(request):
    return render(request, 'core/strategies.html')


def trading_page(request):
    return render(request, 'core/trading.html')


def backtesting_page(request):
    return render(request, 'core/backtesting.html')


def predictions_page(request):
    return render(request, 'core/predictions.html')


def performance_page(request):
    return render(request, 'core/performance.html')


def settings_page(request):
    return render(request, 'core/settings.html')


def profile_page(request):
    return render(request, 'core/profile.html')


def terms_page(request):
    return render(request, 'core/terms.html')


def privacy_page(request):
    return render(request, 'core/privacy.html')


def risk_page(request):
    return render(request, 'core/risk.html')


def billing_success_page(request):
    return render(request, 'core/billing_success.html')


def billing_cancel_page(request):
    return render(request, 'core/billing_cancel.html')


def deriv_login(request):
    if not settings.DERIV_OAUTH_CLIENT_ID or not settings.DERIV_REDIRECT_URI:
        oauth_logger.error("deriv_oauth_misconfigured", extra={"has_client_id": bool(settings.DERIV_OAUTH_CLIENT_ID)})
        return HttpResponse("Deriv OAuth is not configured.", status=503)

    verifier = secrets.token_urlsafe(64)

    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                verifier.encode()
            ).digest()
        )
        .decode()
        .rstrip("=")
    )

    state = secrets.token_urlsafe(32)

    # OAuth/PKCE correlation values must be per-browser-session. Module-level
    # globals leak across users and workers, breaking callback integrity in
    # production deployments.
    request.session["oauth_state"] = state
    request.session["pkce_verifier"] = verifier
    request.session["oauth_redirect_uri"] = settings.DERIV_REDIRECT_URI
    request.session.modified = True

    query = urlencode({
        "response_type": "code",
        "client_id": settings.DERIV_OAUTH_CLIENT_ID,
        "redirect_uri": settings.DERIV_REDIRECT_URI,
        "scope": "trade",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    url = f"{DERIV_AUTHORIZE_URL}?{query}"
    oauth_logger.info("deriv_oauth_started", extra={"redirect_host": urlparse(settings.DERIV_REDIRECT_URI).netloc})

    return redirect(url)

def callback(request):

    received_state = request.GET.get("state")

    expected_state = request.session.get("oauth_state")

    if not received_state or not expected_state or not secrets.compare_digest(received_state, expected_state):
        oauth_logger.warning("deriv_oauth_state_mismatch", extra={"has_received_state": bool(received_state), "has_expected_state": bool(expected_state)})
        return HttpResponse("OAuth state validation failed.", status=400)
    
    code = request.GET.get("code")

    if not code:
        oauth_logger.warning("deriv_oauth_missing_code")
        return HttpResponse("No authorization code received.", status=400)

    verifier = request.session.get("pkce_verifier")
    redirect_uri = request.session.get("oauth_redirect_uri")
    if not verifier or redirect_uri != settings.DERIV_REDIRECT_URI:
        oauth_logger.warning("deriv_oauth_pkce_or_redirect_validation_failed", extra={"has_verifier": bool(verifier)})
        return HttpResponse("OAuth callback integrity validation failed.", status=400)

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.DERIV_OAUTH_CLIENT_ID,
        "redirect_uri": settings.DERIV_REDIRECT_URI,
        "code_verifier": verifier,
    }
    try:
        token_response = requests.post(DERIV_TOKEN_URL, data=token_payload, timeout=OAUTH_TIMEOUT)
        token_response.raise_for_status()
        token_data = token_response.json()
    except requests.Timeout:
        oauth_logger.exception("deriv_oauth_token_timeout")
        return HttpResponse("Deriv OAuth token exchange timed out.", status=504)
    except requests.RequestException:
        oauth_logger.exception("deriv_oauth_token_network_error")
        return HttpResponse("Deriv OAuth token exchange failed.", status=502)
    except ValueError:
        oauth_logger.exception("deriv_oauth_invalid_json")
        return HttpResponse("Deriv returned an invalid OAuth response.", status=502)

    if not isinstance(token_data, dict) or not token_data.get("access_token"):
        oauth_logger.error("deriv_oauth_missing_access_token", extra={"keys": sorted(token_data.keys()) if isinstance(token_data, dict) else []})
        return HttpResponse("Deriv OAuth response did not include an access token.", status=502)

    from django.utils import timezone
    from datetime import timedelta
    from rest_framework_simplejwt.tokens import RefreshToken

    account_id = token_data.get('account_id') or token_data.get('client_id') or None
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = int(token_data.get('expires_in', 3600))
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    user = None
    try:
        if request.user.is_authenticated:
            user = request.user

        if not user:
            if account_id:
                username = f"deriv_{account_id}"
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': f'{account_id}@deriv.local',
                        'first_name': 'Deriv',
                        'last_name': account_id,
                    }
                )
            else:
                # Create a fallback anonymous user
                username = f"deriv_{secrets.token_hex(8)}"
                user = User.objects.create_user(
                    username=username,
                    email=f'{username}@deriv.local',
                    password=User.objects.make_random_password()
                )

        if not hasattr(user, 'trading_profile'):
            from core.models import UserProfile, Subscription, BotSettings
            UserProfile.objects.create(user=user)
            Subscription.objects.create(user=user)
            BotSettings.objects.create(user=user)

        DerivAccount.objects.update_or_create(
            user=user,
            defaults={
                'account_id': account_id or 'unknown',
                'access_token': access_token or '',
                'refresh_token': refresh_token or '',
                'expires_at': expires_at,
            }
        )
        for key in ("oauth_state", "pkce_verifier", "oauth_redirect_uri"):
            request.session.pop(key, None)
        request.session.modified = True
        oauth_logger.info("deriv_oauth_completed", extra={"user_id": user.id, "account_id": account_id})

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        refresh_token_jwt = str(refresh)

        dashboard_redirect = f'/dashboard/?access={access}&refresh={refresh_token_jwt}'
        return redirect(dashboard_redirect)
    except Exception as exc:
        oauth_logger.exception("deriv_oauth_callback_failed")
        return HttpResponse(
            "FAILED TO COMPLETE DERIV CALLBACK",
            status=500
        )
