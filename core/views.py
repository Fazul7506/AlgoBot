import secrets
import hashlib
import base64

import requests
from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.contrib.auth.models import User

from trading.models import DerivAccount
import core.oauth_store as oauth_store


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

    oauth_store.oauth_state = state
    oauth_store.pkce_verifier = verifier

    url = (
        "https://auth.deriv.com/oauth2/auth"
        f"?response_type=code"
        f"&client_id={settings.DERIV_OAUTH_CLIENT_ID}"
        f"&redirect_uri={settings.DERIV_REDIRECT_URI}"
        f"&scope=trade"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )

    return redirect(url)

def callback(request):

    received_state = request.GET.get("state")

    expected_state = oauth_store.oauth_state

    print("RECEIVED:", received_state)
    print("EXPECTED:", expected_state)

    if received_state != expected_state:
        return HttpResponse(
            f"FAILED\n\nReceived: {received_state}\nExpected: {expected_state}"
        )
    
    code = request.GET.get("code")

    if not code:
        return HttpResponse(
            "No authorization code received."
        )

    verifier = oauth_store.pkce_verifier

    token_response = requests.post(
        "https://auth.deriv.com/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.DERIV_OAUTH_CLIENT_ID,
            "redirect_uri": settings.DERIV_REDIRECT_URI,
            "code_verifier": verifier,
        }
    )

    token_data = token_response.json()

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

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        refresh_token_jwt = str(refresh)

        dashboard_redirect = f'/dashboard/?access={access}&refresh={refresh_token_jwt}'
        return redirect(dashboard_redirect)
    except Exception as exc:
        return HttpResponse(
            f"FAILED TO COMPLETE DERIV CALLBACK: {str(exc)}\n\n{token_data}",
            status=500
        )
